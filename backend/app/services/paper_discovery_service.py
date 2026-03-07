"""
Paper-Driven Dataset Discovery Service
---------------------------------------
Searches academic papers (IEEE Xplore + ArXiv + Semantic Scholar) to extract
dataset names actually used by researchers. These names become
extra search seeds for the retrieval orchestrator.

Precedence: IEEE Xplore > ArXiv > Semantic Scholar

Flow:
  Query → Paper Search → Extract Dataset Names → Return as seeds
"""
import re
import json
import asyncio
import logging
import xml.etree.ElementTree as ET
import os
import time
import sqlite3
from typing import List, Dict, Any

import httpx

from app.config import IEEE_API_KEY

logger = logging.getLogger(__name__)

# ── Paper Search API Endpoints ──────────────────────────────────────────────
IEEE_API_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_API_URL = "https://export.arxiv.org/api/query"

# ── Dataset name extraction patterns ────────────────────────────────────────
DATASET_PATTERNS = [
    # "evaluated on the DRIVE dataset"
    r"(?:evaluated|tested|trained|validated|benchmarked|benchmarking)\s+(?:on|using|with|via)\s+(?:the\s+)?(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][A-Za-z0-9\-_]+){0,2})\s*(?:dataset|benchmark|corpus|data|set|collection)",
    # "DRIVE dataset"
    r"(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][A-Za-z0-9\-_]+){0,2})\s+(?:dataset|benchmark|corpus|data set|challenge)",
    # "dataset called DRIVE"
    r"(?:dataset|benchmark|corpus|set)\s+(?:called|named|known\s+as|referred\s+to\s+as)\s+(\b[A-Z][A-Za-z0-9\-_]+)",
    # "using CIFAR-10 and ImageNet"
    r"(?:using|on|with)\s+(?:the\s+)?(\b[A-Z][A-Za-z0-9\-]+(?:\-\d+)?)\s+(?:and|,)\s+(?:[A-Z][A-Za-z0-9\-]+)",
    # "datasets: X, Y, Z"
    r"(?:datasets?|benchmarks?|data)(?:\s*:|\s+include|\s+consist\s+of)\s+(\b[A-Z][A-Za-z0-9\-_]+(?:(?:\s*,\s*|\s+and\s+)[A-Z][A-Za-z0-9\-_]+)*)",
    # Acronyms in parentheses near 'dataset'
    r"(\b[A-Z][A-Z0-9]{1,})\s*\((?:the\s+)?dataset\)",
    # "Proposed X dataset"
    r"(?:proposed|introduced|released|publish)\s+(?:the\s+)?(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][A-Za-z0-9\-_]+){0,2})\s*(?:dataset|benchmark)",
    # Aggressive pattern: CAPITALIZED name before "dataset/challenge"
    r"(\b[A-Z][A-Za-z0-9\-_]+)\s+(?:dataset|challenge|benchmark|competition|benchmark dataset|evaluation set)",
    # Pattern: "X, a large-scale dataset"
    r"(\b[A-Z][A-Za-z0-9\-_]+)\s*,\s*(?:a|an)\s+(?:new|large|public|open|benchmark)\s*(?:-scale)?\s*dataset",
    # solo Capitalized Name in a list of datasets
    r"(?:datasets?|benchmarks?):?\s*(\b[A-Z][A-Za-z0-9\-_]+)(?:\s*,\s*\b[A-Z][A-Za-z0-9\-_]+)*",
    # "evaluated on X" (aggressive)
    r"(?:evaluated|tested|benchmarked)\s+on\s+(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][A-Za-z0-9\-_]+){0,1})",
    # Additional common patterns (Fix 16-point plan)
    r"(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][a-z0-9]+)*)\s+(?:corpus|benchmark|collection|speech dataset|audio dataset|benchmark dataset)",
]

# Common false positives to filter out
FALSE_POSITIVES = {
    # English words that match patterns
    "We", "The", "Our", "This", "In", "For", "An", "A", "It", "Its",
    "As", "At", "By", "On", "Or", "If", "To", "Up", "So", "No",
    "Despite", "Dataset", "Open", "Source", "Using", "Table", "Figure",
    "Results", "Methods", "Analysis", "Proposed", "Current", "New",
    "Public", "Experimental", "Extracted", "Used", "Given", "Base",
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

    def __init__(self):
        self.cache_dir = "cache/papers"
        os.makedirs(self.cache_dir, exist_ok=True)
        self.db_path = os.path.join(self.cache_dir, "papers_cache.db")
        self.cache_ttl = 86400  # 24 hours
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database for paper caching."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_cache (
                    query_key TEXT PRIMARY KEY,
                    data TEXT,
                    timestamp REAL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite cache: {e}")

    async def discover(self, api_query: str, request=None, max_papers: int = 50) -> List[Dict[str, Any]]:
        """
        Search papers and extract rich dataset metadata with caching.
        Primary cache: SQLite, Secondary/Legacy: JSON.
        """
        async def check_abort():
            if request and await request.is_disconnected():
                logger.info(f"Paper Discovery: Client disconnected. Aborting search for '{api_query[:40]}'")
                raise asyncio.CancelledError()

        await check_abort()
        discovered = []
        cache_key = re.sub(r'[^a-zA-Z0-9]', '_', api_query).lower()
        
        # 1. Check SQLite Cache
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT data, timestamp FROM paper_cache WHERE query_key = ?", (cache_key,))
            row = cursor.fetchone()
            if row:
                data_json, timestamp = row
                if time.time() - timestamp < self.cache_ttl:
                    logger.info(f"SQLite Paper Cache HIT: {api_query}")
                    conn.close()
                    return json.loads(data_json)
            conn.close()
        except Exception as e:
            logger.warning(f"SQLite cache read error: {e}")

        # 2. Check JSON Legacy Cache (Fallback)
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.json")
        if os.path.exists(cache_path):
            if time.time() - os.path.getmtime(cache_path) < self.cache_ttl:
                try:
                    with open(cache_path, "r") as f:
                        logger.info(f"JSON Paper Cache HIT: {api_query}")
                        # Migrate to SQLite
                        data = json.load(f)
                        self._save_to_sqlite(cache_key, data)
                        return data
                except Exception as e:
                    logger.warning(f"JSON Cache read error: {e}")

        # 3. Search
        papers = await self._search_papers(api_query, max_papers)
        
        if not papers:
            logger.info("Paper discovery: no papers found, using fallback seed.")
            fallback = api_query if "dataset" in api_query.lower() else f"{api_query} dataset"
            return [{"name": api_query, "seed": fallback}]
        
        discovered = self._extract_all_dataset_metadata(papers)
        
        if not discovered:
            fallback = api_query if "dataset" in api_query.lower() else f"{api_query} dataset"
            return [{"name": api_query, "seed": fallback}]
            
        final_results = discovered[:30]

        # 4. Save to both caches (User request: save in .db)
        self._save_to_sqlite(cache_key, final_results)
        
        try:
            with open(cache_path, "w") as f:
                json.dump(final_results, f)
        except Exception as e:
            logger.warning(f"JSON Cache write error: {e}")
        
        logger.info(
            f"Paper discovery found {len(final_results)} dataset seeds with context."
        )
        return final_results

    def _save_to_sqlite(self, cache_key: str, data: List[Dict[str, Any]]):
        """Helper to save discovery results to SQLite."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO paper_cache (query_key, data, timestamp) VALUES (?, ?, ?)",
                (cache_key, json.dumps(data), time.time())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"SQLite cache save error: {e}")

    async def _search_papers(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Search IEEE Xplore > ArXiv > Semantic Scholar. Merge results."""
        # Run all three in parallel for speed
        ieee_papers, arxiv_papers, s2_papers = await asyncio.gather(
            self._search_ieee(query, limit),
            self._search_arxiv(query, limit),
            self._search_semantic_scholar(query, limit),
            return_exceptions=True,
        )
        
        # Merge with IEEE first (highest priority)
        papers = []
        for source_name, result in [("IEEE", ieee_papers), ("ArXiv", arxiv_papers), ("SemanticScholar", s2_papers)]:
            if isinstance(result, list):
                logger.info(f"Paper discovery [{source_name}]: {len(result)} papers found.")
                papers.extend(result)
            else:
                logger.warning(f"{source_name} error: {result}")
        
        # Deduplicate by title similarity
        seen_titles = set()
        unique = []
        for p in papers:
            title_key = re.sub(r'[^a-z0-9]', '', p.get("title", "").lower())
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique.append(p)
        
        return unique  # Return all unique papers from all tools (each tool already limited)

    async def _search_ieee(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Search IEEE Xplore Metadata API (highest priority)."""
        if not IEEE_API_KEY:
            logger.info("IEEE API key not set, skipping IEEE Xplore search.")
            return []
        
        try:
            clean_q = re.sub(r'[^a-zA-Z0-9\s]', '', query).strip()
            search_text = f"{clean_q} dataset"
            
            params = {
                "apikey": IEEE_API_KEY,
                "querytext": search_text,
                "max_records": min(limit, 25),  # IEEE max is 200 per call, default 25
                "sort_field": "article_title",
                "sort_order": "asc",
            }
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(IEEE_API_URL, params=params)
                
                if resp.status_code != 200:
                    logger.warning(f"IEEE API returned status {resp.status_code}")
                    return []
                
                data = resp.json()
                articles = data.get("articles", [])
                
                papers = []
                for article in articles:
                    title = article.get("title", "").strip()
                    abstract = article.get("abstract", "").strip()
                    
                    # Get citation count from IEEE if available
                    citing_count = article.get("citing_paper_count", 0)
                    if isinstance(citing_count, str):
                        try:
                            citing_count = int(citing_count)
                        except ValueError:
                            citing_count = 0
                    
                    # Build URL
                    article_number = article.get("article_number", "")
                    url = f"https://ieeexplore.ieee.org/document/{article_number}" if article_number else ""
                    
                    # Year from publication_date or publication_year
                    year = article.get("publication_year", "")
                    if not year:
                        pub_date = article.get("publication_date", "")
                        if pub_date:
                            year = pub_date.split(" ")[-1] if " " in pub_date else pub_date[:4]
                    
                    if title and abstract:
                        papers.append({
                            "title": title,
                            "abstract": abstract,
                            "url": url,
                            "year": str(year) if year else None,
                            "citations": citing_count,
                            "source": "ieee",
                        })
                
                logger.info(f"IEEE Xplore returned {len(papers)} papers for '{search_text[:40]}'.")
                return papers
                
        except Exception as e:
            logger.warning(f"IEEE Xplore search error: {e}")
            return []

    async def _safe_request(self, client, url, params):
        """Fix: Semantic Scholar Rate Limit Retry."""
        for _ in range(3):
            resp = await client.get(url, params=params)
            if resp.status_code != 429:
                return resp
            logger.info("Semantic Scholar rate-limited (429), retrying in 2s...")
            await asyncio.sleep(2)
        return resp

    async def _search_semantic_scholar(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Search Semantic Scholar free API."""
        try:
            # Broaden query for better coverage
            search_q = f"{query} dataset benchmark"
            params = {
                "query": search_q,
                "limit": limit,
                "fields": "title,abstract,url,year,citationCount"
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await self._safe_request(client, S2_SEARCH_URL, params)
                if response.status_code == 200:
                    data = response.json()
                    papers = [
                        {
                            "title": p.get("title", ""), 
                            "abstract": p.get("abstract", ""),
                            "url": p.get("url"),
                            "year": str(p.get("year")) if p.get("year") else None,
                            "citations": p.get("citationCount", 0),
                            "source": "semantic_scholar"
                        } for p in data.get("data", [])
                    ]
                    
                    # Fallback if 0 results
                    if not papers and " " in query:
                        parts = query.split()[:2]
                        fallback_q = f"{' '.join(parts)} dataset"
                        params["query"] = fallback_q
                        response = await self._safe_request(client, S2_SEARCH_URL, params)
                        if response.status_code == 200:
                            data = response.json()
                            papers = [{"title": p.get("title", ""), "abstract": p.get("abstract", "")} for p in data.get("data", [])]
                    
                    return papers
                elif response.status_code == 429:
                    logger.info("Semantic Scholar rate-limited (429), will use ArXiv.")
                    return []
                else:
                    logger.warning(f"Semantic Scholar returned {response.status_code}")
                    return []
        except Exception as e:
            logger.warning(f"Semantic Scholar search error: {e}")
            return []

    async def _search_arxiv(self, query: str, limit: int) -> List[Dict[str, str]]:
        """ArXiv paper search (always runs, not just fallback)."""
        try:
            # Clean query for ArXiv
            clean_q = re.sub(r'[^a-zA-Z0-9\s]', '', query).strip()
            
            # Build field-specific search
            if " " in clean_q:
                q_parts = clean_q.split()
                field_q = " AND ".join([f"(ti:{p} OR abs:{p})" for p in q_parts[:3]])
                search_query = f"({field_q}) AND (abs:dataset OR ti:dataset OR abs:benchmark)"
            else:
                search_query = f"all:{clean_q} AND (abs:dataset OR abs:benchmark)"

            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {
                    "search_query": search_query,
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
                    arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/")[-1]
                    url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
                    
                    # Try to get year from published date
                    published = entry.findtext("atom:published", "", ns)
                    year = published[:4] if published else None

                    if title and abstract:
                        papers.append({
                            "title": title, 
                            "abstract": abstract,
                            "url": url,
                            "year": year,
                            "citations": 0,
                            "source": "arxiv"
                        })
                
                # Fallback if 10 results from ArXiv but 0 matches
                if not papers and " " in clean_q:
                    q_words = clean_q.split()[:2]
                    fallback_q = " AND ".join([f"(ti:{w} OR abs:{w})" for w in q_words])
                    params["search_query"] = f"({fallback_q}) AND (dataset OR benchmark)"
                    resp = await client.get(ARXIV_API_URL, params=params)
                    if resp.status_code == 200:
                        root = ET.fromstring(resp.text)
                        for entry in root.findall("atom:entry", ns):
                            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
                            abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
                            if title and abstract:
                                papers.append({"title": title, "abstract": abstract})
                
                return papers
        except Exception as e:
            logger.warning(f"ArXiv search failed: {e}")
            return []

    def _extract_all_dataset_metadata(self, papers: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Extract and analyze dataset metadata from all papers."""
        seen_names = {}
        
        for paper in papers:
            text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
            mentions = self._extract_mentions_with_context(text)
            
            for name, context in mentions:
                if name in FALSE_POSITIVES or len(name) < 3:
                    continue
                
                # Deduplicate and merge information
                if name not in seen_names:
                    # Basic analysis of context
                    purpose = "research"
                    if any(kw in context.lower() for kw in ["robustness", "resilience", "robust"]):
                        purpose = "robustness evaluation"
                    elif any(kw in context.lower() for kw in ["benchmark", "standard", "baseline"]):
                        purpose = "benchmark"
                    elif "fairness" in context.lower():
                        purpose = "fairness evaluation"

                    modality = "unknown"
                    if any(kw in context.lower() for kw in ["image", "vision", "pixel", "cnn", "satellite", "aerial", "remote sensing", "lidar"]):
                        modality = "image"
                    elif any(kw in context.lower() for kw in ["text", "nlp", "corpus", "sentence", "language model"]):
                        modality = "text"
                    elif any(kw in context.lower() for kw in ["multimodal", "vqa", "vision-language", "audio-visual"]):
                        modality = "multimodal"
                    
                    # ── Extract Size & Annotations (UI Improvement) ──
                    ds_size = None
                    if "images" in context.lower():
                        size_match = re.search(r"(\d+(?:,\d+)?)\s+images", context.lower())
                        if size_match: ds_size = f"{size_match.group(1)} images"
                    elif "samples" in context.lower():
                        size_match = re.search(r"(\d+(?:,\d+)?)\s+samples", context.lower())
                        if size_match: ds_size = f"{size_match.group(1)} samples"

                    ann_type = None
                    if any(kw in context.lower() for kw in ["segmentation", "masks", "pixel-wise"]):
                        ann_type = "Segmentation masks"
                    elif any(kw in context.lower() for kw in ["bounding boxes", "boxes", "detection"]):
                        ann_type = "Bounding boxes"
                    elif "labels" in context.lower():
                        ann_type = "Classification labels"

                    seen_names[name] = {
                        "name": name,
                        "seed": f"{name} dataset",
                        "purpose": purpose,
                        "modality": modality,
                        "context": context[:250],
                        "paper_title": paper.get("title"),
                        "paper_url": paper.get("url"),
                        "paper_source": paper.get("source", "arxiv"),
                        "year": str(paper.get("year")) if paper.get("year") else None,
                        "citations": paper.get("citations", 0),
                        "dataset_size": ds_size,
                        "annotation_type": ann_type
                    }
        
        return list(seen_names.values())

    def _extract_mentions_with_context(self, text: str) -> List[tuple]:
        """Find dataset names and return them with surrounding context."""
        found = []
        for pattern in DATASET_PATTERNS:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip()
                # Get window of context
                start = max(0, match.start() - 60)
                end = min(len(text), match.end() + 100)
                context = text[start:end]
                found.append((name, context))
        return found

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
                        if part and len(part) > 3 and part[0].isupper() and part not in FALSE_POSITIVES:
                            mentions.add(part)
                else:
                    match = match.strip()
                    if match and len(match) > 3 and match not in FALSE_POSITIVES:
                        mentions.add(match)
        
        return list(mentions)


# Need asyncio for parallel search
import asyncio

# Module singleton
paper_discovery = PaperDiscoveryService()
