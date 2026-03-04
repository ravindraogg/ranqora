"""
arXiv dataset extraction tool.
Searches arXiv for papers related to the query and extracts
dataset references from titles and summaries.
Uses the free arXiv Atom API — no credentials needed.
"""

import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

import httpx

from app.services.retrieval.base_tool import BaseRetrievalTool


ARXIV_API_URL = "http://export.arxiv.org/api/query"


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
        search_query = f"all:{query} AND (abs:dataset OR abs:benchmark)"

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
                return []
            xml_content = response.text

        return self._parse_arxiv_response(xml_content)

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
        """Simple heuristic: find capitalized words near 'dataset'/'benchmark'."""
        dataset_mentions = []
        patterns = [
            r"(\b[A-Z][A-Za-z0-9\-]+(?:\s[A-Z][A-Za-z0-9\-]+)*)\s+(?:dataset|benchmark|corpus)",
            r"(?:dataset|benchmark|corpus)\s+(?:called|named|known as)\s+(\b[A-Z][A-Za-z0-9\-]+)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dataset_mentions.extend(matches)
        # Deduplicate
        return list(set(dataset_mentions))[:5]
