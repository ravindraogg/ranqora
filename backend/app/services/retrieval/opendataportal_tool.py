"""
Open Data Portal connector.
Searches data.gov (CKAN-based) for public government / open datasets.
No authentication required.
"""

import httpx
import re
from typing import List, Dict, Any

from app.services.retrieval.base_tool import BaseRetrievalTool


DATAGOV_API_URL = "https://catalog.data.gov/api/3/action/package_search"


class OpenDataPortalRetrievalTool(BaseRetrievalTool):
    name = "opendataportal"
    description = "Search open government datasets on data.gov"
    supported_domains = ["general", "tabular", "time-series", "geospatial", "public-policy"]

    async def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search data.gov catalog.
        Increased default limit (if called directly) to ensure better coverage.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # CKAN search params
            params = {
                "q": query,
                "rows": limit,
                "sort": "score desc, metadata_modified desc" # Prioritize relevance + freshness
            }
            try:
                response = await client.get(DATAGOV_API_URL, params=params)
                if response.status_code != 200:
                    return []
                data = response.json()
            except Exception:
                return []

        results = []
        for pkg in data.get("result", {}).get("results", []):
            results.append(self._normalize(pkg))
        return results

    @staticmethod
    def _normalize(raw: dict) -> Dict[str, Any]:
        # Handle description (notes) and strip HTML
        raw_notes = raw.get("notes", "") or "No description"
        clean_desc = re.sub(r'<[^>]+>', '', raw_notes) # Strip basic HTML tags
        
        # Real popularity metrics from CKAN tracking_summary
        # mapping recent views to 'likes' and total views to 'downloads' for ranking compatibility
        tracking = raw.get("tracking_summary", {})
        likes = tracking.get("recent", 0)
        downloads = tracking.get("total", 0)
        
        # Gather more informative tags from resources (formats) and organization
        tags = [tag.get("display_name", "") for tag in raw.get("tags", [])]
        for res in raw.get("resources", []):
            fmt = res.get("format", "").upper()
            if fmt and fmt not in tags:
                tags.append(fmt)
        
        # Organization info as source-context
        org = raw.get("organization", {}).get("title", "")
        if org and org not in tags:
            tags.append(org)

        return {
            "id": raw.get("name", "") or raw.get("id", ""),
            "source": "opendataportal",
            "description": clean_desc[:500],
            "downloads": downloads,
            "likes": likes,
            "url": f"https://catalog.data.gov/dataset/{raw.get('name', '')}",
            "license": raw.get("license_title") or "U.S. Government Public Work",
            "last_modified": raw.get("metadata_modified", ""),
            "tags": tags[:12], # Keep tag list reasonable
            "org_name": org
        }
