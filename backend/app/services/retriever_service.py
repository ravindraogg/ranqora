import httpx
from app.config import HUGGINGFACE_API_URL, MAX_DATASETS_TO_FETCH

async def fetch_huggingface_datasets(query: str):
    """
    Fetch candidate datasets from Hugging Face based on the query.
    """
    async with httpx.AsyncClient() as client:
        # Use simple search endpoint to get candidate datasets
        params = {
            "search": query,
            "limit": MAX_DATASETS_TO_FETCH,
            "full": "true" 
        }
        response = await client.get(HUGGINGFACE_API_URL, params=params)
        response.raise_for_status()
        
        datasets = response.json()
        
        # Filter out datasets without descriptions for semantic ranking
        results = []
        for dataset in datasets:
            desc = dataset.get("description", "")
            if desc:
                results.append({
                    "id": dataset.get("id"),
                    "description": desc,
                    "downloads": dataset.get("downloads", 0),
                    "likes": dataset.get("likes", 0)
                })
                
        return results