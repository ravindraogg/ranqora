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

    @staticmethod
    def simplify_query(query: str) -> str:
        """Removes common Kaggle search blockers."""
        stopwords = [
            "dataset",
            "recognition",
            "classification",
            "deep learning",
            "model"
        ]
        q = query.lower()
        for w in stopwords:
            q = q.replace(w, "")
        return " ".join(q.split())

    async def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        auth_params = self._get_auth_params()
        if not auth_params:
            return []

        # Multi-query strategy to increase recall on Kaggle (exact match engine)
        queries = list(dict.fromkeys([
            query,
            self.simplify_query(query),
            query.replace("dataset", "").strip()
        ]))
        
        all_datasets = {}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for q in queries:
                if not q:
                    continue
                # Pagination: page 1 and 2 with 20 results each to bypass cap
                for page in range(1, 3):
                    params = {
                        "search": q,
                        "page": page,
                        "pageSize": 20,
                        "sortBy": "relevance",
                    }
                    try:
                        response = await client.get(
                            f"{KAGGLE_API_BASE}/datasets/list",
                            params=params,
                            **auth_params
                        )
                        if response.status_code == 200:
                            batch = response.json()
                            for ds in batch:
                                normalized = self._normalize(ds)
                                all_datasets[normalized["id"]] = normalized
                    except Exception:
                        continue 

        return list(all_datasets.values())[:limit]

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
