from pydantic import BaseModel
from typing import List, Optional, Dict


# ─── Request Models ──────────────────────────────────────────────

class ProjectContext(BaseModel):
    query: str
    client_id: str
    domain: Optional[str] = None
    tasks: Optional[List[str]] = None


class FeedbackEvent(BaseModel):
    query: str
    dataset_id: str
    event_type: str  # click, download, or bookmark
    dwell_time_ms: Optional[int] = 0

# ─── Response Models ─────────────────────────────────────────────

class DatasetMetadata(BaseModel):
    id: str
    source: str = "huggingface"
    description: str
    downloads: int = 0
    likes: int = 0
    url: str = ""
    license: str = "unknown"
    last_modified: str = ""
    tags: List[str] = []
    similarity_score: float = 0.0
    ranking_breakdown: Optional[Dict[str, float]] = None


class RetrievalPlan(BaseModel):
    tools: List[str]
    limits: Dict[str, int]
    reasoning: str


class DatasetRankingResponse(BaseModel):
    datasets: List[DatasetMetadata]
    plan: Optional[RetrievalPlan] = None
    source_counts: Optional[Dict[str, int]] = None
    total_candidates: int = 0
    errors: Optional[List[Dict[str, str]]] = None
    status: str

class DatasetPreview(BaseModel):
    type: str  # tabular, nlp, image
    columns: Optional[List[str]] = None
    rows: Optional[List[Dict[str, Optional[str]]]] = None
    image_urls: Optional[List[str]] = None
    text_samples: Optional[List[str]] = None
    file_structure: Optional[List[str]] = None

class DatasetDetailResponse(BaseModel):
    metadata: Optional[DatasetMetadata] = None
    preview: Optional[DatasetPreview] = None
    redirect_url: str
    estimated_download_time: Optional[str] = None
    size_bytes: Optional[int] = None
    size_readable: Optional[str] = None
