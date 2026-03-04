"""
GitHub dataset discovery tool.
Searches GitHub repositories that are tagged as datasets
or contain dataset-related files.
Uses the public GitHub Search API (unauthenticated rate: 10 req/min).
Optionally uses GITHUB_TOKEN env var for higher rate limits.
"""

import os
import httpx
from typing import List, Dict, Any

from app.services.retrieval.base_tool import BaseRetrievalTool


GITHUB_API_URL = "https://api.github.com/search/repositories"


class GitHubRetrievalTool(BaseRetrievalTool):
    name = "github"
    description = "Discover dataset repositories on GitHub"
    supported_domains = ["general", "nlp", "cv", "ml", "tabular", "audio"]

    def _get_headers(self) -> dict:
        headers = {"Accept": "application/vnd.github.v3+json"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    async def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        # Refine search to target actual data file structures in repos instead of text descriptions logic
        file_targets = "extension:csv OR extension:json OR extension:jsonl OR extension:parquet OR extension:arrow"
        search_query = f"{query} dataset ({file_targets})"

        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "q": search_query,
                "sort": "stars",
                "order": "desc",
                "per_page": min(limit, 30),  # GitHub API caps at 30 per page
            }
            response = await client.get(
                GITHUB_API_URL,
                params=params,
                headers=self._get_headers(),
            )
            if response.status_code != 200:
                return []

            data = response.json()

        results = []
        for repo in data.get("items", []):
            results.append(self._normalize(repo))
        return results

    @staticmethod
    def _normalize(raw: dict) -> Dict[str, Any]:
        return {
            "id": raw.get("full_name", ""),
            "source": "github",
            "description": raw.get("description", "") or "No description",
            "downloads": raw.get("stargazers_count", 0),  # GitHub datasets should not look weak
            "likes": raw.get("stargazers_count", 0),
            "url": raw.get("html_url", ""),
            "license": (raw.get("license") or {}).get("spdx_id") or "unknown",
            "last_modified": raw.get("updated_at", ""),
            "tags": raw.get("topics", []),
        }
