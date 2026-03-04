import os
import io
import pandas as pd
import requests
import logging
from typing import Dict, Any, List, Optional
from app.config import KAGGLE_API_TOKEN, KAGGLE_USERNAME, KAGGLE_KEY

logger = logging.getLogger(__name__)

class DatasetPreviewService:
    def __init__(self):
        self.max_preview_size = 1024 * 1024  # 1MB Hard Limit

    def get_dataset_details(self, dataset_id: str, source: str) -> Dict[str, Any]:
        """
        Fetches full metadata and a preview for a dataset.
        """
        details = {
            "redirect_url": "",
            "preview": None,
            "size_bytes": 0,
            "size_readable": "Unknown",
            "estimated_download_time": "Unknown"
        }

        if source == "kaggle":
            return self._get_kaggle_details(dataset_id, details)
        elif source == "huggingface":
            return self._get_hf_details(dataset_id, details)
        
        return details

    def _get_kaggle_details(self, dataset_id: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch details from Kaggle API."""
        url = f"https://www.kaggle.com/api/v1/datasets/view/{dataset_id}"
        auth = self._get_kaggle_auth()
        
        try:
            response = requests.get(url, auth=auth, headers=self._get_kaggle_headers())
            response.raise_for_status()
            data = response.json()
            
            details["redirect_url"] = f"https://www.kaggle.com/datasets/{dataset_id}"
            details["size_bytes"] = data.get("totalBytes", 0)
            details["size_readable"] = self._format_size(details["size_bytes"])
            details["estimated_download_time"] = self._estimate_download_time(details["size_bytes"])
            
            # Deep Scan for file structure
            file_list = []
            for key, value in data.items():
                if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                    if "name" in value[0]:
                        file_list = [f.get("name", "") for f in value]
                        break
            
            csv_files = [f for f in file_list if str(f).endswith(".csv")]
            
            # Only claim tabular if there are csvs (and we won't serve empty rows array to frontend)
            if csv_files:
                details["preview"] = {
                    "type": "tabular", 
                    "file_structure": file_list[:20],
                    # Omit columns and rows unless we actually fetch them, so frontend skips rendering empty tables
                }
            else:
                details["preview"] = {
                    "type": "media", 
                    "file_structure": file_list[:20],
                }

        except Exception as e:
            logger.error(f"Error fetching Kaggle details: {e}")
            
        return details

    def _get_hf_details(self, dataset_id: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch details from HuggingFace."""
        url = f"https://huggingface.co/api/datasets/{dataset_id}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            details["redirect_url"] = f"https://huggingface.co/datasets/{dataset_id}"
            details["size_readable"] = "Varies" 
            
            file_list = [s.get("rfilename", "") for s in data.get("siblings", [])]
            
            # Check if text data
            if any(f.endswith(".parquet") or f.endswith(".jsonl") for f in file_list):
                 details["preview"] = {
                    "type": "nlp",
                    "file_structure": file_list[:20],
                }
            else:
                 details["preview"] = {
                    "type": "media",
                    "file_structure": file_list[:20],
                }
        except Exception as e:
            logger.error(f"Error fetching HF details: {e}")
            
        return details

    def _get_kaggle_auth(self):
        if KAGGLE_USERNAME and KAGGLE_KEY:
            return (KAGGLE_USERNAME, KAGGLE_KEY)
        return None

    def _get_kaggle_headers(self):
        if KAGGLE_API_TOKEN:
            return {"Authorization": f"Bearer {KAGGLE_API_TOKEN}"}
        return {}

    def _format_size(self, bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024
        return f"{bytes:.2f} PB"

    def _estimate_download_time(self, bytes: int) -> str:
        # Assume 5MB/s average speed
        seconds = bytes / (5 * 1024 * 1024)
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes = seconds / 60
        if minutes < 60:
            return f"{int(minutes)}m"
        hours = minutes / 60
        return f"{int(hours)}h {int(minutes % 60)}m"

preview_service = DatasetPreviewService()
