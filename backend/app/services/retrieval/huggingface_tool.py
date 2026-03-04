"""
HuggingFace dataset retrieval tool.
Searches the Hugging Face Hub API for datasets matching a query.
"""

import httpx
import logging
from typing import List, Dict, Any

from app.services.retrieval.base_tool import BaseRetrievalTool
from app.config import HUGGINGFACE_API_URL

logger = logging.getLogger(__name__)


class HuggingFaceRetrievalTool(BaseRetrievalTool):
    name = "huggingface"
    description = "Search datasets on Hugging Face Hub"
    supported_domains = ["general", "nlp", "cv", "audio", "multimodal", "tabular"]

    async def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search HuggingFace with progressive keyword fallback.
        Tries the full query, then each individual word, deduplicates by id.
        """
        seen_ids: set = set()
        results: List[Dict[str, Any]] = []

        # Build a list of queries to try: full phrase first, then individual keywords
        keywords = [w for w in query.split() if len(w) > 3]  # skip tiny words
        search_variants = [query] + keywords  # e.g. ["retinal image", "retinal", "image"]

        async with httpx.AsyncClient(timeout=45.0) as client:
            for i, term in enumerate(search_variants):
                if len(results) >= limit:
                    break
                # Only fallback if full query returns < 10 results
                if i > 0 and len(results) >= 10:
                    break
                try:
                    params = {
                        "search": term,
                        "limit": limit,
                        "full": "true",
                    }
                    response = await client.get(HUGGINGFACE_API_URL, params=params)
                    response.raise_for_status()
                    datasets = response.json()

                    for ds in datasets:
                        ds_id = ds.get("id", "")
                        if not ds_id or ds_id in seen_ids:
                            continue
                        seen_ids.add(ds_id)
                        desc = (
                            ds.get("description")
                            or (ds.get("cardData") or {}).get("description")
                            or ""
                        )
                        if not desc:
                            desc = ds_id  # minimal fallback
                        results.append(self._normalize(ds, desc))

                        if len(results) >= limit:
                            break
                except Exception as e:
                    logger.warning(f"HuggingFace search failed for term '{term}': {e}")
                    continue

        return results

    @staticmethod
    def _normalize(raw: dict, description: str) -> Dict[str, Any]:
        # Strip tag prefixes like "license:mit" -> "mit", "task_categories:classification"
        raw_tags = raw.get("tags", [])
        clean_tags = []
        for t in raw_tags:
            if ":" in t:
                val = t.split(":", 1)[1]
                # Skip noisy size / region / library tags
                if not any(val.startswith(p) for p in ("n<", "n>", "us", "eu", "datasets", "mlcroissant")):
                    clean_tags.append(val)
            else:
                clean_tags.append(t)

        card = raw.get("cardData") or {}
        raw_license = card.get("license") or "unknown"
        # cardData.license can be a list ["mit"] or a string "mit"
        if isinstance(raw_license, list):
            raw_license = raw_license[0] if raw_license else "unknown"

        return {
            "id": raw.get("id", ""),
            "source": "huggingface",
            "description": description,
            "downloads": raw.get("downloads", 0),
            "likes": raw.get("likes", 0),
            "url": f"https://huggingface.co/datasets/{raw.get('id', '')}",
            "license": str(raw_license),
            "last_modified": raw.get("lastModified", ""),
            "tags": clean_tags[:10],
        }
