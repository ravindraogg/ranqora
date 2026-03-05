"""
arXiv dataset extraction tool.
Searches arXiv for papers related to the query and extracts
dataset references from titles and summaries.
Uses the free arXiv Atom API — no credentials needed.
"""

import re
import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Any

import httpx

logger = logging.getLogger(__name__)

from app.services.retrieval.base_tool import BaseRetrievalTool


ARXIV_API_URL = "https://export.arxiv.org/api/query"


class ArxivRetrievalTool(BaseRetrievalTool):
    name = "arxiv"
    description = "Extract dataset references from arXiv papers"
    supported_domains = ["general", "nlp", "cv", "ml", "audio", "multimodal"]

    # Common dataset keywords to look for in paper content
    DATASET_KEYWORDS = [
        "dataset", "benchmark", "corpus", "data set", "training data",
        "evaluation data", "test set", "labeled data", "annotations",
    ]

    async def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        # Clean query: ArXiv doesn't like special characters
        clean_q = re.sub(r'[^a-zA-Z0-9\s]', '', query).strip()
        
        # Build field-specific query: searching title and abstract specifically is better
        # if the query is more than a couple of words.
        if " " in clean_q:
            q_parts = clean_q.split()
            # Combine words into a more permissive OR/AND structure for ArXiv
            field_q = " AND ".join([f"(ti:{p} OR abs:{p})" for p in q_parts[:4]])
            search_query = f"({field_q}) AND (abs:dataset OR ti:dataset OR abs:benchmark)"
        else:
            search_query = f"all:{clean_q} AND (abs:dataset OR abs:benchmark)"

        logger.info(f"ArXiv tool searching with: {search_query}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "search_query": search_query,
                    "start": 0,
                    "max_results": limit,
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                }
                response = await client.get(ARXIV_API_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"ArXiv API returned status {response.status_code}")
                    return []
                xml_content = response.text
                
                results = self._parse_arxiv_response(xml_content)
                
                # If 0 results, try a broader fallback search with just the first 2 words
                if not results and " " in clean_q:
                    logger.info("ArXiv fallback search (broader)")
                    q_words = clean_q.split()[:2]
                    fallback_q = " AND ".join([f"(ti:{w} OR abs:{w})" for w in q_words])
                    params["search_query"] = f"({fallback_q}) AND (dataset OR benchmark)"
                    response = await client.get(ARXIV_API_URL, params=params)
                    if response.status_code == 200:
                        results = self._parse_arxiv_response(response.text)
                
                return results
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            return []

    def _parse_arxiv_response(self, xml_content: str) -> List[Dict[str, Any]]:
        """Parse the Atom XML response and extract dataset-like entries."""
        results = []
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return results

        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
            published = entry.findtext("atom:published", "", ns)

            # Get the paper link
            link = ""
            for link_el in entry.findall("atom:link", ns):
                if link_el.get("type") == "text/html":
                    link = link_el.get("href", "")
                    break
            if not link:
                id_text = entry.findtext("atom:id", "", ns)
                link = id_text

            # Extract dataset names mentioned in the paper
            dataset_names = self._extract_dataset_names(title + " " + summary)

            results.append({
                "id": f"arxiv:{title[:80]}",
                "source": "arxiv",
                "description": summary[:500],
                "downloads": 0,
                "likes": 0,
                "url": link,
                "license": "arxiv-paper",
                "last_modified": published,
                "tags": dataset_names if dataset_names else ["research", "paper"],
            })

        return results

    @staticmethod
    def _extract_dataset_names(text: str) -> List[str]:
        """Extract dataset names from paper text for tagging."""
        mentions = set()
        patterns = [
            # "evaluated on the DRIVE dataset"
            r"(?:evaluated|tested|trained|validated|benchmarked)\s+(?:on|using|with|via)\s+(?:the\s+)?(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][A-Za-z0-9\-_]+){0,2})\s*(?:dataset|benchmark|corpus|data|set|collection)",
            # "DRIVE dataset"
            r"(\b[A-Z][A-Za-z0-9\-_]+(?:\s[A-Z][A-Za-z0-9\-_]+){0,2})\s+(?:dataset|benchmark|corpus|data set|challenge)",
            # "dataset called DRIVE"
            r"(?:dataset|benchmark|corpus|set)\s+(?:called|named|known\s+as|referred\s+to\s+as)\s+(\b[A-Z][A-Za-z0-9\-_]+)",
            # Acronyms in parentheses
            r"(\b[A-Z][A-Z0-9]{1,})\s*\((?:the\s+)?dataset\)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                m = m.strip()
                if len(m) > 1 and m[0].isupper():
                    mentions.add(m)
        
        return list(mentions)[:5]
