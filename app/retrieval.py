from __future__ import annotations

from datetime import datetime
from typing import List

from .models import DatasetMetadata


def search_huggingface_datasets(query: str, limit: int = 40) -> List[DatasetMetadata]:
    from huggingface_hub import list_datasets

    datasets: List[DatasetMetadata] = []
    for item in list_datasets(search=query, limit=limit, full=True):
        card_data = getattr(item, "cardData", {}) or {}
        datasets.append(
            DatasetMetadata(
                id=item.id,
                name=item.id.split("/")[-1],
                description=(
                    card_data.get("pretty_name")
                    or card_data.get("description")
                    or f"Dataset {item.id}"
                ),
                tags=list(getattr(item, "tags", []) or []),
                likes=getattr(item, "likes", 0) or 0,
                downloads=getattr(item, "downloads", 0) or 0,
                last_modified=_parse_datetime(getattr(item, "lastModified", None)),
                license=card_data.get("license") or _extract_license(getattr(item, "tags", []) or []),
            )
        )
    return datasets


def _extract_license(tags: list[str]) -> str | None:
    for tag in tags:
        if tag.startswith("license:"):
            return tag.split(":", 1)[1]
    return None


def _parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
