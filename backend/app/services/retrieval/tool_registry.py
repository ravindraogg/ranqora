"""
Tool Registry: Central registry of all available retrieval tools.
New tools are registered here and auto-discovered by the orchestrator.
"""

from typing import List, Dict

from app.services.retrieval.base_tool import BaseRetrievalTool
from app.services.retrieval.huggingface_tool import HuggingFaceRetrievalTool
from app.services.retrieval.kaggle_tool import KaggleRetrievalTool
from app.services.retrieval.arxiv_tool import ArxivRetrievalTool
from app.services.retrieval.github_tool import GitHubRetrievalTool
from app.services.retrieval.opendataportal_tool import OpenDataPortalRetrievalTool


class ToolRegistry:
    """
    Manages all available retrieval tools.
    Provides methods to list, filter, and retrieve tools by name or domain.
    """

    def __init__(self):
        self._tools: Dict[str, BaseRetrievalTool] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register all built-in retrieval tools."""
        default_tools = [
            KaggleRetrievalTool(),
            ArxivRetrievalTool(),
            HuggingFaceRetrievalTool(),
            GitHubRetrievalTool(),
            OpenDataPortalRetrievalTool(),
        ]
        for tool in default_tools:
            self.register(tool)

    def register(self, tool: BaseRetrievalTool):
        """Register a new retrieval tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseRetrievalTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> List[BaseRetrievalTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def list_names(self) -> List[str]:
        """Return names of all registered tools."""
        return list(self._tools.keys())

    def get_tools_for_domain(self, domain: str | None) -> List[BaseRetrievalTool]:
        """Return tools that support the given domain."""
        return [tool for tool in self._tools.values() if tool.matches_domain(domain)]

    def get_tools_by_names(self, names: List[str]) -> List[BaseRetrievalTool]:
        """Return tools matching the given list of names."""
        return [self._tools[n] for n in names if n in self._tools]

    def describe_tools(self) -> List[Dict[str, str]]:
        """Return a summary of all tools for the planner agent."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "supported_domains": tool.supported_domains,
            }
            for tool in self._tools.values()
        ]


# Global singleton instance
registry = ToolRegistry()
