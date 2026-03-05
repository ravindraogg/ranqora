"""
Kaggle dataset retrieval tool.
Uses the Kaggle public API to search for datasets.
Requires KAGGLE_USERNAME and KAGGLE_KEY environment variables.
"""

import os
import httpx
from typing import List, Dict, Any

from app.services.retrieval.base_tool import BaseRetrievalTool


KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"


class KaggleRetrievalTool(BaseRetrievalTool):
    name = "kaggle"
    description = "Search datasets on Kaggle"
    supported_domains = ["general", "tabular", "cv", "nlp", "time-series"]

    def _get_auth_params(self) -> dict:
        token = os.getenv("KAGGLE_API_TOKEN")
        if token:
            return {"headers": {"Authorization": f"Bearer {token}"}}
            
        username = os.getenv("KAGGLE_USERNAME")
        key = os.getenv("KAGGLE_KEY")
        if username and key:
            return {"auth": (username, key)}
            
        return {}

    async def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        auth_params = self._get_auth_params()
        if not auth_params:
            # Kaggle API requires authentication; return empty if not configured
            return []

        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "search": query,
                "page": 1,
                "pageSize": limit,
                "sortBy": "relevance",
            }
            response = await client.get(
                f"{KAGGLE_API_BASE}/datasets/list",
                params=params,
                **auth_params
            )
            if response.status_code != 200:
                # Silently degrade — don't break the pipeline
                return []
            datasets = response.json()

        results = []
        for ds in datasets:
            results.append(self._normalize(ds))
        return results

    @staticmethod
    def _normalize(raw: dict) -> Dict[str, Any]:
        ref = raw.get("ref", "")
        return {
            "id": ref or raw.get("id", ""),
            "source": "kaggle",
            "description": raw.get("subtitle", "") or raw.get("description", "No description"),
            "downloads": raw.get("downloadCount", 0),
            "likes": raw.get("voteCount", 0),
            "url": f"https://www.kaggle.com/datasets/{ref}" if ref else "",
            "license": raw.get("licenseName", "unknown"),
            "last_modified": raw.get("lastUpdated", ""),
            "tags": [tag.get("name", "") for tag in raw.get("tags", [])],
        }
