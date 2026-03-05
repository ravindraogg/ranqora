"""
Dynamic Retrieval Orchestrator (Phase 3 → Agent-Driven)
---------------------------------------------------------
Now delegates to the DiscoveryAgent for intelligent, memory-driven
iterative exploration instead of brute-force variant searching.

The orchestrator is a thin wrapper that:
  1. Passes context to the DiscoveryAgent
  2. Handles deduplication of the agent's collected results
  3. Returns the standard response format
"""

import re
import logging
from typing import List, Dict, Any

from app.services.agents.discovery_agent import discovery_agent

logger = logging.getLogger(__name__)

# Noise tokens stripped during dedup comparison
_DEDUP_NOISE = {"dataset", "data", "v1", "v2", "v3", "clean", "cleaned",
                "final", "full", "raw", "original", "processed", "new"}


class RetrievalOrchestrator:
    """
    Orchestrates multi-source dataset retrieval via the DiscoveryAgent.
    The agent handles planning, tool selection, and iterative exploration.
    """

    async def retrieve(
        self,
        query: str,
        domain: str | None = None,
        tasks: list[str] | None = None,
        search_query: str | None = None,
        keyword_variants: list[str] | None = None,
        tool_priority: list[str] | None = None,
        limits: dict | None = None,
        emit=None,
    ) -> Dict[str, Any]:
        """
        Full retrieval pipeline, now driven by the DiscoveryAgent.

        Args:
            query:            Full original user sentence.
            search_query:     Primary short keyword phrase for API searches.
            keyword_variants: LLM-suggested search phrases.
            tool_priority:    Preferred tool ordering from LLM.
            limits:           Per-tool fetch limits.
            emit:             Optional async SSE callback.
        """
        api_query = search_query or " ".join(query.split()[:4])
        variants = list(keyword_variants or [])

        # Delegate to the Discovery Agent
        agent_result = await discovery_agent.discover(
            query=query,
            domain=domain or "general",
            tasks=tasks or [],
            search_query=api_query,
            keyword_variants=variants,
            tool_priority=tool_priority,
            limits=limits,
            emit=emit,
        )

        # Deduplicate the agent's collected candidates
        raw_candidates = agent_result["candidates"]
        deduplicated = self._deduplicate(raw_candidates)

        # Recalculate source counts after dedup
        source_counts: Dict[str, int] = {}
        for ds in deduplicated:
            src = ds.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        return {
            "candidates": deduplicated,
            "plan": agent_result["plan"],
            "source_counts": source_counts,
            "total": len(deduplicated),
            "errors": agent_result["errors"],
            "discovery_context": agent_result["discovery_context"],
            "agent_memory": agent_result.get("agent_memory"),
        }

    @staticmethod
    def _token_similarity(name_a: str, name_b: str) -> float:
        """
        Jaccard token overlap — more robust than SequenceMatcher.
        Strips noise tokens before comparison.
        """
        tokens_a = set(re.split(r'[-_/\s.]+', name_a.lower())) - _DEDUP_NOISE
        tokens_b = set(re.split(r'[-_/\s.]+', name_b.lower())) - _DEDUP_NOISE
        # Remove very short tokens
        tokens_a = {t for t in tokens_a if len(t) > 1}
        tokens_b = {t for t in tokens_b if len(t) > 1}
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

    @staticmethod
    def _deduplicate(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate datasets across sources.
        Uses exact ID match + token-based Jaccard similarity (> 0.75).
        Prefers the candidate with higher download count.
        """
        seen: Dict[str, Dict[str, Any]] = {}
        name_index: Dict[str, str] = {}  # base_name -> canonical_ds_id

        for ds in candidates:
            ds_id = ds.get("id", "")
            if not ds_id:
                continue

            # 1. Exact ID match
            if ds_id in seen:
                existing = seen[ds_id]
                if ds.get("downloads", 0) > existing.get("downloads", 0):
                    seen[ds_id] = ds
                continue

            # 2. Token-based similarity clustering
            parts = re.split(r'[/_]', ds_id)
            base_name = parts[-1] if parts else ds_id
            if len(base_name) < 5:
                base_name = ds_id

            matched_canonical_id = None
            for existing_name, existing_id in name_index.items():
                similarity = RetrievalOrchestrator._token_similarity(base_name, existing_name)
                if similarity > 0.75:
                    matched_canonical_id = existing_id
                    break

            if matched_canonical_id and matched_canonical_id in seen:
                existing_ds = seen[matched_canonical_id]
                if ds.get("downloads", 0) > existing_ds.get("downloads", 0):
                    del seen[matched_canonical_id]
                    seen[ds_id] = ds
                    name_index[base_name] = ds_id
            else:
                seen[ds_id] = ds
                name_index[base_name] = ds_id

        return list(seen.values())


# Module-level singleton
orchestrator = RetrievalOrchestrator()
