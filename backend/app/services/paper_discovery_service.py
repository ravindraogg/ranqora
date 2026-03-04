"""
Paper-Driven Dataset Discovery Service
---------------------------------------
Searches academic papers (Semantic Scholar + ArXiv) to extract
dataset names actually used by researchers. These names become
extra search seeds for the retrieval orchestrator.

Flow:
  Query → Paper Search → Extract Dataset Names → Return as seeds
"""

import re
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# Semantic Scholar free API (no key needed for basic search)
S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_API_URL = "http://export.arxiv.org/api/query"

# ── Dataset name extraction patterns ────────────────────────────────────────
DATASET_PATTERNS = [
    # "evaluated on the DRIVE dataset"
    r"(?:evaluated|tested|trained|validated|benchmarked)\s+(?:on|using|with)\s+(?:the\s+)?(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][A-Za-z0-9\-_]+){0,2})\s*(?:dataset|benchmark|corpus|data)",
    # "DRIVE dataset"
    r"(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][A-Za-z0-9\-_]+){0,2})\s+(?:dataset|benchmark|corpus)",
    # "dataset called DRIVE"
    r"(?:dataset|benchmark|corpus)\s+(?:called|named|known\s+as)\s+(\b[A-Z][A-Za-z0-9\-_]+)",
    # "using CIFAR-10 and ImageNet"
    r"(?:using|on|with)\s+(?:the\s+)?(\b[A-Z][A-Za-z0-9\-]+(?:\-\d+)?)\s+(?:and|,)",
    # "datasets: X, Y, Z"
    r"(?:datasets?|benchmarks?)(?:\s*:|\s+include)\s+(\b[A-Z][A-Za-z0-9\-_]+(?:(?:\s*,\s*|\s+and\s+)[A-Z][A-Za-z0-9\-_]+)*)",
]

# Common false positives to filter out
FALSE_POSITIVES = {
    # English words that match patterns
    "We", "The", "Our", "This", "In", "For", "An", "A", "It", "Its",
    "As", "At", "By", "On", "Or", "If", "To", "Up", "So", "No",
    "All", "Any", "Are", "But", "Can", "Did", "Do", "Get", "Got",
    "Had", "Has", "Her", "Him", "His", "How", "Its", "May", "New",
    "Now", "Old", "One", "Out", "Own", "Per", "Set", "Two", "Use",
    "Was", "Way", "Who", "Why", "Yet",
    "Each", "From", "Have", "Here", "Into", "Just", "Like", "Make",
    "Many", "More", "Most", "Much", "Must", "Next", "Only", "Over",
    "Such", "Than", "That", "Then", "They", "Very", "What", "When",
    "With", "Also", "Some", "Will", "Both", "Used", "Based", "Given",
    "First", "Second", "Third", "Large", "Small", "These", "Those",
    "Other", "After", "Before", "Every", "While", "Where", "About",
    "Using", "Current", "Several", "Recent", "Previous", "Proposed",
    "Different", "Various", "Existing", "Specific", "Multiple",

    # Paper section names
    "Table", "Figure", "Section", "Appendix", "Results", "Methods",
    "Conclusion", "Abstract", "Introduction", "Related", "Experiments",
    "Discussion", "Evaluation", "Analysis",

    # ML model names (not datasets)
    "CNN", "RNN", "GAN", "LSTM", "BERT", "GPT", "ResNet", "VGG",
    "Adam", "SGD", "ViT", "CLIP", "SAM", "LLaMA", "Llama",
    "Transformer", "Attention", "Encoder", "Decoder",

    # Venue names
    "IEEE", "CVPR", "ICCV", "ECCV", "NeurIPS", "ICML", "AAAI",
    "ACL", "EMNLP", "NAACL", "ICLR", "SIGIR", "KDD", "WWW",

    # Generic ML terms
    "State", "Deep", "Neural", "Machine", "Learning", "Model",
    "Network", "Architecture", "Framework", "Method", "Approach",
    "Performance", "Accuracy", "Training", "Fine", "Pre",
}


class PaperDiscoveryService:
    """Discovers datasets referenced in academic papers."""

    async def discover(self, query: str, max_papers: int = 10) -> List[str]:
        """
        Search papers and extract dataset names.
        
        Returns a list of dataset name strings to be used as search seeds.
        Example: ["DRIVE dataset", "CHASE_DB1 dataset", "IDRiD dataset"]
        """
        papers = await self._search_papers(query, max_papers)
        
        if not papers:
            logger.info("Paper discovery: no papers found, skipping.")
            return []
        
        dataset_names = self._extract_all_dataset_names(papers)
        
        logger.info(
            f"Paper discovery: {len(papers)} papers → "
            f"{len(dataset_names)} dataset seeds: {dataset_names}"
        )
        return dataset_names

    async def _search_papers(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Search both Semantic Scholar AND ArXiv, merge results."""
        # Run both in parallel for speed
        s2_papers, arxiv_papers = await asyncio.gather(
            self._search_semantic_scholar(query, limit),
            self._search_arxiv(query, limit),
            return_exceptions=True,
        )
        
        papers = []
        if isinstance(s2_papers, list):
            papers.extend(s2_papers)
        else:
            logger.warning(f"Semantic Scholar error: {s2_papers}")
            
        if isinstance(arxiv_papers, list):
            papers.extend(arxiv_papers)
        else:
            logger.warning(f"ArXiv error: {arxiv_papers}")
        
        # Deduplicate by title similarity
        seen_titles = set()
        unique = []
        for p in papers:
            title_key = re.sub(r'[^a-z0-9]', '', p.get("title", "").lower())
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique.append(p)
        
        return unique[:limit]

    async def _search_semantic_scholar(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Search Semantic Scholar free API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {
                    "query": f"{query} dataset benchmark",
                    "limit": limit,
                    "fields": "title,abstract,year,citationCount",
                }
                resp = await client.get(S2_SEARCH_URL, params=params)
                if resp.status_code == 429:
                    logger.info("Semantic Scholar rate-limited (429), will use ArXiv.")
                    return []
                if resp.status_code != 200:
                    logger.warning(f"Semantic Scholar returned {resp.status_code}")
                    return []

                data = resp.json()
                papers = []
                for paper in data.get("data", []):
                    title = paper.get("title", "")
                    abstract = paper.get("abstract", "")
                    if title and abstract:
                        papers.append({
                            "title": title,
                            "abstract": abstract,
                            "citations": paper.get("citationCount", 0),
                        })
                return papers
        except Exception as e:
            logger.warning(f"Semantic Scholar search failed: {e}")
            return []

    async def _search_arxiv(self, query: str, limit: int) -> List[Dict[str, str]]:
        """ArXiv paper search (always runs, not just fallback)."""
        try:
            search_query = f"all:{query} AND (abs:dataset OR abs:benchmark)"
            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {
                    "search_query": search_query,
                    "start": 0,
                    "max_results": limit,
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                }
                resp = await client.get(ARXIV_API_URL, params=params)
                if resp.status_code != 200:
                    return []

                ns = {"atom": "http://www.w3.org/2005/Atom"}
                root = ET.fromstring(resp.text)
                papers = []
                for entry in root.findall("atom:entry", ns):
                    title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
                    abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
                    if title and abstract:
                        papers.append({"title": title, "abstract": abstract, "citations": 0})
                return papers
        except Exception as e:
            logger.warning(f"ArXiv search failed: {e}")
            return []

    def _extract_all_dataset_names(self, papers: List[Dict[str, str]]) -> List[str]:
        """Extract and deduplicate dataset names from all papers."""
        all_names = set()
        
        for paper in papers:
            text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
            names = self._extract_dataset_names(text)
            all_names.update(names)
        
        # Filter false positives, short names, and common English words
        filtered = []
        for name in all_names:
            # Skip if in blocklist
            if name in FALSE_POSITIVES:
                continue
            # Skip if too short (< 3 chars) — except known acronyms
            if len(name) < 3:
                continue
            # Skip common English words (all lowercase after first letter)
            if len(name) <= 6 and name[0].isupper() and name[1:].islower():
                # Could be a common word like "Current", "Several", etc.
                if name.lower() in {w.lower() for w in FALSE_POSITIVES}:
                    continue
            # Skip if it looks like a generic adjective/noun
            if name.lower() in {"large", "small", "new", "real", "raw", "full",
                                "clean", "original", "standard", "public", "open",
                                "complete", "entire", "whole", "custom"}:
                continue
            filtered.append(name)
        
        # Append "dataset" to each name for better search results
        seeds = [f"{name} dataset" for name in filtered]
        
        return seeds[:15]  # Cap at 15 seeds

    @staticmethod
    def _extract_dataset_names(text: str) -> List[str]:
        """Extract dataset names from a single paper's text."""
        mentions = set()
        
        for pattern in DATASET_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                # Handle comma-separated lists
                if "," in match or " and " in match:
                    parts = re.split(r"\s*,\s*|\s+and\s+", match)
                    for part in parts:
                        part = part.strip()
                        if part and part[0].isupper() and part not in FALSE_POSITIVES:
                            mentions.add(part)
                else:
                    match = match.strip()
                    if match and match not in FALSE_POSITIVES:
                        mentions.add(match)
        
        return list(mentions)


# Need asyncio for parallel search
import asyncio

# Module singleton
paper_discovery = PaperDiscoveryService()
