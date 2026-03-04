"""
Base class for all retrieval tools.
Every dataset source (HuggingFace, Kaggle, arXiv, GitHub, OpenData)
must inherit from this and implement the `search` method.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseRetrievalTool(ABC):
    """Abstract base class defining the interface for all retrieval tools."""

    name: str = "base"
    description: str = "Base retrieval tool"
    # Domains this tool is strong at (e.g. "nlp", "cv", "tabular", "general")
    supported_domains: List[str] = ["general"]

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for datasets matching the query.

        Returns a list of normalized dicts with at minimum:
            - id: str
            - source: str        (e.g. "huggingface", "kaggle")
            - description: str
            - downloads: int
            - likes: int
            - url: str
            - license: str
            - last_modified: str
            - tags: List[str]
        """
        ...

    def matches_domain(self, domain: str | None) -> bool:
        """Check if this tool is relevant for the given domain."""
        if domain is None:
            return True
        return "general" in self.supported_domains or domain.lower() in [
            d.lower() for d in self.supported_domains
        ]
