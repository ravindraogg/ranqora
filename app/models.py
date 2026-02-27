from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ProjectQuery(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    abstract: str = Field(..., min_length=10, max_length=4000)
    top_k: int = Field(default=7, ge=1, le=20)


class DatasetMetadata(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    likes: int = 0
    downloads: int = 0
    last_modified: Optional[datetime] = None
    license: Optional[str] = None
    source: str = "huggingface"

    def ranking_text(self) -> str:
        tags = ", ".join(self.tags)
        return f"{self.name}. {self.description}. Tags: {tags}. License: {self.license or 'unknown'}"


class RankedDataset(BaseModel):
    dataset: DatasetMetadata
    score: float
    rank: int


class RankingResponse(BaseModel):
    query: str
    total_candidates: int
    ranked: List[RankedDataset]
