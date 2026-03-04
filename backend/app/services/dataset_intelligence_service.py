"""
Dataset Intelligence Layer
--------------------------
Classifies every dataset candidate with structured metadata:
  - type: review, image, tabular, dialogue, instruction, code, audio, other
  - domain: nlp, cv, audio, tabular, general
  - format: text, csv, image, audio, multimodal

Used by ranking_service to add type_match and format_match signals,
preventing semantic drift (e.g. recipe datasets matching medical queries).
"""

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# ── Type Classification Keywords ────────────────────────────────────────────
TYPE_KEYWORDS: Dict[str, List[str]] = {
    "review": [
        "review", "rating", "feedback", "opinion", "sentiment",
        "customer feedback", "user review", "product review", "star rating",
        "comment", "testimonial",
    ],
    "image": [
        "image", "photo", "photograph", "picture", "pixel", "visual",
        "frame", "segmentation mask", "bounding box", "annotation",
        "x-ray", "ct scan", "mri", "fundus", "retinal", "satellite",
    ],
    "tabular": [
        "csv", "table", "column", "row", "spreadsheet", "structured",
        "excel", "sql", "database", "record", "field", "numeric",
        "regression", "feature",
    ],
    "dialogue": [
        "dialogue", "conversation", "chat", "support ticket", "qa",
        "question answer", "chatbot", "helpdesk", "customer support",
        "multi-turn", "response",
    ],
    "instruction": [
        "instruct", "instruction", "prompt", "completion", "fine-tune",
        "fine tuning", "sft", "rlhf", "alignment", "preference",
        "alpaca", "dolly", "sharegpt",
    ],
    "code": [
        "code", "programming", "source code", "github", "repository",
        "function", "snippet", "bug", "commit", "pull request",
        "python", "javascript", "java",
    ],
    "audio": [
        "audio", "speech", "sound", "voice", "music", "acoustic",
        "waveform", "spectrogram", "asr", "tts", "transcript",
        "spoken", "podcast", "recording",
    ],
}

# ── Domain Classification Keywords ─────────────────────────────────────────
DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "nlp": [
        "text", "language", "nlp", "corpus", "document", "sentence",
        "word", "token", "review", "sentiment", "translation",
        "summarization", "ner", "entity", "topic", "comment",
        "instruction", "prompt", "dialogue",
    ],
    "cv": [
        "image", "visual", "photo", "video", "pixel", "segmentation",
        "detection", "recognition", "classification", "frame",
        "bounding box", "mask", "retinal", "fundus", "x-ray",
        "satellite", "medical imaging",
    ],
    "audio": [
        "audio", "speech", "voice", "sound", "music", "acoustic",
        "asr", "tts", "waveform", "spectrogram",
    ],
    "tabular": [
        "tabular", "csv", "table", "structured", "column", "row",
        "feature", "numeric", "regression", "excel", "sql",
    ],
}

# ── Format Detection Keywords ──────────────────────────────────────────────
FORMAT_KEYWORDS: Dict[str, List[str]] = {
    "text": [
        "text", "txt", "json", "jsonl", "parquet", "document",
        "corpus", "sentence", "paragraph",
    ],
    "csv": [
        "csv", "tsv", "excel", "spreadsheet", "table",
    ],
    "image": [
        "image", "jpg", "jpeg", "png", "tiff", "dicom",
        "nifti", "bmp", "gif",
    ],
    "audio": [
        "audio", "wav", "mp3", "flac", "ogg", "waveform",
    ],
    "multimodal": [
        "multimodal", "multi-modal", "image-text", "video-text",
        "audio-text", "vision-language",
    ],
}

# ── Domain-to-Type Compatibility ───────────────────────────────────────────
# Which dataset types are compatible with which query domains
DOMAIN_TYPE_COMPAT: Dict[str, set] = {
    "nlp": {"review", "dialogue", "instruction", "code", "other"},
    "cv": {"image", "other"},
    "audio": {"audio", "other"},
    "tabular": {"tabular", "other"},
    "general": {"review", "image", "tabular", "dialogue", "instruction", "code", "audio", "other"},
    "time-series": {"tabular", "other"},
    "multimodal": {"image", "review", "dialogue", "instruction", "audio", "other"},
}

# ── Domain-to-Format Compatibility ─────────────────────────────────────────
DOMAIN_FORMAT_COMPAT: Dict[str, set] = {
    "nlp": {"text", "csv", "multimodal"},
    "cv": {"image", "multimodal"},
    "audio": {"audio", "multimodal"},
    "tabular": {"csv", "text"},
    "general": {"text", "csv", "image", "audio", "multimodal"},
}


class DatasetIntelligenceService:
    """Classifies datasets with structured metadata for filtering and ranking."""

    def classify(self, ds: Dict[str, Any]) -> Dict[str, str]:
        """
        Classify a dataset candidate.
        
        Returns:
            {"type": "review", "domain": "nlp", "format": "text"}
        """
        ds_text = self._build_text(ds)
        
        return {
            "type": self._classify_type(ds_text),
            "domain": self._classify_domain(ds_text),
            "format": self._classify_format(ds_text),
        }

    def type_match_score(self, ds: Dict[str, Any], query_domain: str | None) -> float:
        """
        Returns 1.0 if dataset type is compatible with query domain.
        Returns 0.3 if incompatible (strong penalty).
        Returns 0.7 if ambiguous.
        """
        if not query_domain or query_domain == "general":
            return 1.0
        
        ds_text = self._build_text(ds)
        ds_type = self._classify_type(ds_text)
        
        compatible_types = DOMAIN_TYPE_COMPAT.get(query_domain, set())
        
        if ds_type in compatible_types:
            return 1.0
        elif ds_type == "other":
            return 0.7  # Unknown type — don't penalize too hard
        else:
            return 0.3  # Wrong type for this domain

    def format_match_score(
        self, ds: Dict[str, Any], preferred_format: str | None
    ) -> float:
        """
        Returns 1.0 if dataset format matches preferred format.
        Returns 0.5 if no preferred format or ambiguous.
        """
        if not preferred_format or preferred_format == "any":
            return 0.7
        
        ds_text = self._build_text(ds)
        ds_format = self._classify_format(ds_text)
        
        # Normalize preferred format
        pf = preferred_format.lower()
        
        if ds_format == "multimodal":
            return 0.8  # Multimodal is generally flexible
        
        # Check if formats align
        if ds_format in pf or pf in ds_format:
            return 1.0
        
        # CSV matches text, image matches image, etc.
        format_groups = {
            "text": {"text", "csv", "json", "jsonl", "parquet"},
            "image": {"image", "jpg", "png"},
            "audio": {"audio", "wav", "mp3"},
        }
        
        for group_name, group_formats in format_groups.items():
            if ds_format in group_formats and any(f in pf for f in group_formats):
                return 0.9
        
        return 0.5

    @staticmethod
    def _build_text(ds: Dict[str, Any]) -> str:
        """Build searchable text from dataset fields."""
        return " ".join([
            ds.get("id", ""),
            ds.get("description", "")[:500],
            " ".join(ds.get("tags", [])),
        ]).lower()

    @staticmethod
    def _classify_type(text: str) -> str:
        """Classify dataset type by keyword counting."""
        scores = {}
        for dtype, keywords in TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[dtype] = score
        
        if not scores:
            return "other"
        
        return max(scores, key=scores.get)

    @staticmethod
    def _classify_domain(text: str) -> str:
        """Classify dataset domain."""
        scores = {}
        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[domain] = score
        
        if not scores:
            return "general"
        
        return max(scores, key=scores.get)

    @staticmethod
    def _classify_format(text: str) -> str:
        """Classify dataset format."""
        scores = {}
        for fmt, keywords in FORMAT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[fmt] = score
        
        if not scores:
            return "text"  # Default assumption
        
        return max(scores, key=scores.get)


# Module singleton
dataset_intelligence = DatasetIntelligenceService()
