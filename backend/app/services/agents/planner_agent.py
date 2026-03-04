"""
Planner Agent (Phase 2)
-----------------------
Analyzes the user's project context (query, domain, tasks) and decides
which retrieval tools to activate and in what priority order.

This is a rule-based planner for Phase 2.
In later phases it can be replaced with an LLM-based planner.
"""

from typing import List, Dict, Any
from app.services.retrieval.tool_registry import registry


# Domain-to-tool priority mapping
# Higher-priority tools are listed first
DOMAIN_TOOL_PRIORITY: Dict[str, List[str]] = {
    "nlp": ["huggingface", "arxiv", "kaggle", "github", "opendataportal"],
    "cv": ["huggingface", "kaggle", "arxiv", "github", "opendataportal"],
    "audio": ["huggingface", "arxiv", "github", "kaggle", "opendataportal"],
    "tabular": ["kaggle", "opendataportal", "huggingface", "github", "arxiv"],
    "time-series": ["kaggle", "opendataportal", "huggingface", "arxiv", "github"],
    "geospatial": ["opendataportal", "kaggle", "github", "huggingface", "arxiv"],
    "multimodal": ["huggingface", "arxiv", "github", "kaggle", "opendataportal"],
    "ml": ["huggingface", "kaggle", "arxiv", "github", "opendataportal"],
    "public-policy": ["opendataportal", "kaggle", "github", "huggingface", "arxiv"],
}

# Default priority when domain is unknown
DEFAULT_PRIORITY = ["huggingface", "kaggle", "arxiv", "github", "opendataportal"]

# Keywords that hint at specific sources
SOURCE_KEYWORDS: Dict[str, List[str]] = {
    "kaggle": ["competition", "kaggle", "tabular", "csv", "structured"],
    "arxiv": ["paper", "research", "benchmark", "state-of-the-art", "sota"],
    "github": ["repository", "github", "code", "implementation", "open-source"],
    "opendataportal": ["government", "census", "public", "federal", "policy", "open data"],
    "huggingface": ["transformer", "huggingface", "llm", "pretrained", "model"],
}


class PlannerAgent:
    """
    Decides which retrieval tools to use and in what order
    based on the project context.
    """

    def plan(
        self,
        query: str,
        domain: str | None = None,
        tasks: list[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Generate a retrieval plan.

        Returns:
            {
                "tools": ["huggingface", "kaggle", ...],  # ordered by priority
                "limits": {"huggingface": 20, "kaggle": 15, ...},
                "reasoning": "explanation of tool selection"
            }
        """
        selected_tools = self._select_tools(query, domain, tasks)
        limits = self._assign_limits(selected_tools)
        reasoning = self._build_reasoning(selected_tools, domain, query)

        return {
            "tools": selected_tools,
            "limits": limits,
            "reasoning": reasoning,
        }

    def _select_tools(
        self,
        query: str,
        domain: str | None,
        tasks: list[str] | None,
    ) -> List[str]:
        """Select and order tools based on domain and query keywords."""
        # Start with domain-based priority
        if domain and domain.lower() in DOMAIN_TOOL_PRIORITY:
            priority = DOMAIN_TOOL_PRIORITY[domain.lower()].copy()
        else:
            priority = DEFAULT_PRIORITY.copy()

        # Boost tools based on keyword matches in the query
        query_lower = query.lower()
        boost_scores: Dict[str, int] = {tool: 0 for tool in priority}

        for tool_name, keywords in SOURCE_KEYWORDS.items():
            for kw in keywords:
                if kw in query_lower:
                    boost_scores[tool_name] = boost_scores.get(tool_name, 0) + 1

        # Re-sort priority by boost (stable sort preserves domain-based order for ties)
        priority.sort(key=lambda t: boost_scores.get(t, 0), reverse=True)

        # Only include tools that are actually registered
        available = registry.list_names()
        return [t for t in priority if t in available]

    def _assign_limits(self, tools: List[str]) -> Dict[str, int]:
        """Assign per-tool fetch limits. Target: ~700 candidates total."""
        limits = {}
        # Balanced allocation across tools.
        # Target: ~700 candidates total across up to 5 tools.
        allocations = [180, 150, 150, 120, 100]  # total = 700
        for i, tool in enumerate(tools):
            limits[tool] = allocations[i] if i < len(allocations) else 100
        return limits

    def _build_reasoning(
        self, tools: List[str], domain: str | None, query: str
    ) -> str:
        """Generate a human-readable explanation of the plan."""
        parts = [f"Selected {len(tools)} retrieval tools."]
        if domain:
            parts.append(f"Domain '{domain}' prioritized: {tools[0]} as primary source.")
        else:
            parts.append("No domain specified; using general priority ordering.")
        parts.append(f"Tool order: {' > '.join(tools)}.")
        return " ".join(parts)


# Module-level singleton
planner = PlannerAgent()
