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
    "We", "The", "Our", "This", "In", "For", "Table", "Figure",
    "Section", "Appendix", "Results", "Methods", "Conclusion",
    "Abstract", "Introduction", "Related", "Experiments",
    "CNN", "RNN", "GAN", "LSTM", "BERT", "GPT", "ResNet",
    "VGG", "Adam", "SGD", "IEEE", "CVPR", "ICCV", "ECCV",
    "NeurIPS", "ICML", "AAAI", "ACL", "EMNLP", "NAACL",
    "State", "Deep", "Neural", "Machine", "Learning",
}


class PaperDiscoveryService:
    """Discovers datasets referenced in academic papers."""

    async def discover(self, query: str, max_papers: int = 10) -> List[str]:
        """
        Search papers and extract dataset names.
        
        Returns a list of dataset name strings to be used as search seeds.
        Example: ["DRIVE", "CHASE_DB1", "IDRiD", "Messidor"]
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
        """Search Semantic Scholar, fallback to ArXiv."""
        papers = await self._search_semantic_scholar(query, limit)
        if not papers:
            papers = await self._search_arxiv(query, limit)
        return papers

    async def _search_semantic_scholar(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Search Semantic Scholar free API."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {
                    "query": query,
                    "limit": limit,
                    "fields": "title,abstract,year,citationCount",
                }
                resp = await client.get(S2_SEARCH_URL, params=params)
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
        """Fallback ArXiv search."""
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
            logger.warning(f"ArXiv fallback search failed: {e}")
            return []

    def _extract_all_dataset_names(self, papers: List[Dict[str, str]]) -> List[str]:
        """Extract and deduplicate dataset names from all papers."""
        all_names = set()
        
        for paper in papers:
            text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
            names = self._extract_dataset_names(text)
            all_names.update(names)
        
        # Filter false positives and short names
        filtered = [
            name for name in all_names
            if name not in FALSE_POSITIVES
            and len(name) >= 3
            and not name.isupper() or len(name) <= 8  # Allow short acronyms like "DRIVE"
        ]
        
        # Append "dataset" to each name for better search results
        seeds = [f"{name} dataset" for name in filtered]
        
        return seeds[:15]  # Cap at 15 seeds to avoid overloading retrieval

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


# Module singleton
paper_discovery = PaperDiscoveryService()
