"""
Agent Working Memory
---------------------
Maintains state during the discovery process so the agent can:
  1. Remember what it has already explored
  2. Track which datasets it has found (and from which sources)
  3. Compute real-time confidence to decide when to stop
  4. Expand knowledge based on discoveries (not random brute-force)

This is the key difference between a search pipeline and an AI agent.
"""

import logging
import re
from typing import Dict, List, Any, Set

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Working memory for a single discovery session.
    Created fresh per query — not persisted across requests.
    """

    def __init__(self, query: str, domain: str, tasks: List[str]):
        self.query = query
        self.domain = domain
        self.tasks = tasks

        # ── Discovery State ──
        self.discovered_datasets: Dict[str, Dict[str, Any]] = {}  # id → metadata
        self.explored_queries: Set[str] = set()
        self.explored_tools: Dict[str, Set[str]] = {}  # tool_name → set of queries run
        self.source_hits: Dict[str, int] = {}  # source → count of results

        # ── Confidence Tracking ──
        self.high_confidence_count: int = 0
        self.cross_source_datasets: Set[str] = set()  # datasets found on 2+ sources
        self.paper_backed_datasets: Set[str] = set()  # datasets cited in papers

        # ── Agent Reasoning Log ──
        self.reasoning_log: List[str] = []
        self.iteration_count: int = 0

    # ── Core Operations ──────────────────────────────────────────────────────

    def record_exploration(self, query: str, tool_name: str, results: List[Dict]):
        """Record that a query was explored with a specific tool."""
        self.explored_queries.add(query)
        if tool_name not in self.explored_tools:
            self.explored_tools[tool_name] = set()
        self.explored_tools[tool_name].add(query)

        for ds in results:
            ds_id = ds.get("id", "")
            if not ds_id:
                continue

            source = ds.get("source", "unknown")
            self.source_hits[source] = self.source_hits.get(source, 0) + 1

            if ds_id in self.discovered_datasets:
                # Cross-source validation: dataset found on multiple platforms
                existing_source = self.discovered_datasets[ds_id].get("source", "")
                if existing_source != source:
                    self.cross_source_datasets.add(ds_id)
                # Keep the version with more downloads
                if ds.get("downloads", 0) > self.discovered_datasets[ds_id].get("downloads", 0):
                    self.discovered_datasets[ds_id] = ds
            else:
                self.discovered_datasets[ds_id] = ds

    def record_paper_discovery(self, dataset_names: List[str]):
        """Record datasets found in academic papers."""
        for name in dataset_names:
            self.paper_backed_datasets.add(name.lower())

    def log_reasoning(self, message: str):
        """Add a reasoning trace to the agent log."""
        self.reasoning_log.append(f"[Iter {self.iteration_count}] {message}")
        logger.info(f"Agent reasoning: {message}")

    # ── Intelligence Queries ─────────────────────────────────────────────────

    def get_unique_dataset_count(self) -> int:
        """Number of unique datasets discovered so far."""
        return len(self.discovered_datasets)

    def get_high_confidence_datasets(self) -> List[Dict]:
        """
        Datasets with strong signals:
          - Found on multiple sources
          - Backed by research papers
          - High download count
        """
        strong = []
        for ds_id, ds in self.discovered_datasets.items():
            score = 0
            if ds_id in self.cross_source_datasets:
                score += 2
            if ds_id.lower() in self.paper_backed_datasets or any(
                name in ds_id.lower() for name in self.paper_backed_datasets
            ):
                score += 2
            if ds.get("downloads", 0) > 1000:
                score += 1
            if score >= 2:
                strong.append(ds)
        self.high_confidence_count = len(strong)
        return strong

    def compute_session_confidence(self) -> float:
        """
        Real-time confidence estimation for the current session.
        Used by the agent to decide whether to keep searching or stop.

        Formula:
          confidence = (
            0.30 × dataset_coverage     +   # enough datasets found?
            0.25 × source_diversity      +   # multiple sources contributing?
            0.25 × high_confidence_ratio +   # strong signal datasets?
            0.20 × paper_support             # academic backing?
          )
        """
        total = self.get_unique_dataset_count()

        # Coverage: 15+ datasets = 1.0
        coverage = min(total / 15, 1.0)

        # Source diversity: 3+ unique sources = 1.0
        unique_sources = len(set(
            ds.get("source", "unknown") for ds in self.discovered_datasets.values()
        ))
        diversity = min(unique_sources / 3, 1.0)

        # High-confidence ratio
        hc = len(self.get_high_confidence_datasets())
        hc_ratio = min(hc / 5, 1.0) if total > 0 else 0.0

        # Paper support
        paper_support = min(len(self.paper_backed_datasets) / 3, 1.0)

        confidence = (0.30 * coverage) + (0.25 * diversity) + (0.25 * hc_ratio) + (0.20 * paper_support)
        return round(confidence, 3)

    def should_stop(self, min_confidence: float = 0.65, max_iterations: int = 4) -> bool:
        """
        Stopping condition for the agent loop.
        Stop if:
          1. Confidence threshold reached, OR
          2. Maximum iterations exhausted, OR
          3. 5+ high-confidence datasets found
        """
        confidence = self.compute_session_confidence()
        hc_count = self.high_confidence_count

        if confidence >= min_confidence:
            self.log_reasoning(f"STOP: Confidence {confidence:.0%} ≥ {min_confidence:.0%} threshold.")
            return True

        if self.iteration_count >= max_iterations:
            self.log_reasoning(f"STOP: Max iterations ({max_iterations}) reached. Confidence: {confidence:.0%}.")
            return True

        if hc_count >= 5:
            self.log_reasoning(f"STOP: {hc_count} high-confidence datasets found.")
            return True

        return False

    # ── Expansion Suggestions ────────────────────────────────────────────────

    def suggest_expansions(self) -> List[str]:
        """
        Based on what the agent has discovered so far, suggest
        follow-up queries to deepen the search.

        This is the 'agent memory → adaptive exploration' behavior.
        """
        expansions = []

        # 1. Expand paper-backed datasets that aren't yet in our results
        for name in self.paper_backed_datasets:
            # Check if we actually found it
            found = any(name in ds_id.lower() for ds_id in self.discovered_datasets)
            if not found and f"{name} dataset" not in self.explored_queries:
                expansions.append(f"{name} dataset")

        # 2. If a tool has 0 results, don't suggest re-running it
        # (handled by the agent loop)

        # 3. Expand sources for cross-validated datasets
        for ds_id in list(self.cross_source_datasets)[:3]:
            ds = self.discovered_datasets.get(ds_id)
            if ds:
                # Try to find it on platforms we haven't searched
                base_name = ds_id.split("/")[-1] if "/" in ds_id else ds_id
                base_name = re.sub(r'[-_]', ' ', base_name)
                if base_name not in self.explored_queries:
                    expansions.append(base_name)

        return expansions[:5]  # Cap at 5 expansion queries

    def get_all_candidates(self) -> List[Dict]:
        """Return all unique discovered datasets as a flat list."""
        return list(self.discovered_datasets.values())

    def get_summary(self) -> Dict[str, Any]:
        """Summary of the agent's discovery session for the frontend."""
        return {
            "total_discovered": self.get_unique_dataset_count(),
            "queries_explored": len(self.explored_queries),
            "tools_used": list(self.explored_tools.keys()),
            "source_distribution": dict(self.source_hits),
            "cross_validated": len(self.cross_source_datasets),
            "paper_backed": len(self.paper_backed_datasets),
            "session_confidence": self.compute_session_confidence(),
            "iterations": self.iteration_count,
            "reasoning_trace": self.reasoning_log,
        }
