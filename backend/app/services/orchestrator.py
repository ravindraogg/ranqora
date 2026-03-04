"""
Dynamic Retrieval Orchestrator (Phase 3)
-----------------------------------------
Coordinates the full retrieval pipeline:
  1. Paper discovery: extract dataset names from academic papers
  2. Planner selects tools and limits
  3. All selected tools run in parallel (async)
  4. Results are collected, deduplicated (token-based), and normalized
"""

import asyncio
import re
import logging
from typing import List, Dict, Any

from app.services.agents.planner_agent import planner
from app.services.retrieval.tool_registry import registry
from app.services.paper_discovery_service import paper_discovery


logger = logging.getLogger(__name__)

# Noise tokens stripped during dedup comparison
_DEDUP_NOISE = {"dataset", "data", "v1", "v2", "v3", "clean", "cleaned",
                "final", "full", "raw", "original", "processed", "new"}


class RetrievalOrchestrator:
    """
    Orchestrates multi-source dataset retrieval.
    Uses the PlannerAgent to decide which tools to run,
    then executes them concurrently.
    """

    async def retrieve(
        self,
        query: str,
        domain: str | None = None,
        tasks: list[str] | None = None,
        search_query: str | None = None,
        keyword_variants: list[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Full retrieval pipeline.

        Args:
            query:            Full original user sentence (used for semantic ranking).
            search_query:     Primary short keyword phrase for API searches.
            keyword_variants: Additional search phrases — each triggers an extra
                              retrieval pass, results are deduplicated.
        """
        api_query = search_query or " ".join(query.split()[:4])
        variants = list(keyword_variants or [])

        # ── Step 0: Paper-Driven Dataset Discovery ────────────────────
        try:
            paper_seeds = await paper_discovery.discover(api_query)
            if paper_seeds:
                logger.info(f"Paper discovery added {len(paper_seeds)} seeds: {paper_seeds[:5]}...")
                # Prepend paper seeds so they get searched first
                variants = paper_seeds + variants
        except Exception as e:
            logger.warning(f"Paper discovery failed (non-fatal): {e}")

        # Step 1: Plan which tools to use
        plan = planner.plan(query, domain, tasks)
        tool_names = plan["tools"]
        limits = plan["limits"]

        logger.info(f"Retrieval plan: {plan['reasoning']}")
        logger.info(f"Primary API query: '{api_query}' | variants: {len(variants)}")

        # Step 2: Execute primary query across all tools in parallel
        tools = registry.get_tools_by_names(tool_names)

        async def run_pass(term: str) -> list:
            """Run all tools for a single search term."""
            coros = [self._safe_search(t, term, limits.get(t.name, 10)) for t in tools]
            tool_results = await asyncio.gather(*coros)
            results = []
            for tool, res in zip(tools, tool_results):
                if isinstance(res, Exception):
                    logger.warning(f"Tool '{tool.name}' / term '{term}' failed: {res}")
                else:
                    logger.info(f"Tool '{tool.name}' / '{term}': {len(res)} results")
                    results.extend(res)
            return results

        # Primary pass
        primary_results = await run_pass(api_query)

        # Variant passes — stop based on UNIQUE candidates, not raw count
        seen_variants = {api_query}
        all_raw = list(primary_results)
        for variant in variants:
            if variant in seen_variants:
                continue
            seen_variants.add(variant)
            variant_results = await run_pass(variant)
            all_raw.extend(variant_results)
            
            # Smart stopping: check deduplicated count
            unique_count = len(self._deduplicate(all_raw))
            if unique_count >= 500:
                logger.info(f"Stopping retrieval: {unique_count} unique candidates reached.")
                break

        # Step 3: Deduplicate and count per source
        deduplicated = self._deduplicate(all_raw)
        source_counts: Dict[str, int] = {}
        errors: list = []
        for ds in deduplicated:
            src = ds.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        return {
            "candidates": deduplicated,
            "plan": plan,
            "source_counts": source_counts,
            "total": len(deduplicated),
            "errors": errors,
        }


    @staticmethod
    async def _safe_search(tool, query: str, limit: int):
        """Run a tool's search method and catch exceptions gracefully."""
        try:
            logger.info(f"Starting tool '{tool.name}' with query='{query[:50]}', limit={limit}")
            result = await tool.search(query, limit)
            logger.info(f"Tool '{tool.name}' completed successfully with {len(result)} results")
            return result
        except Exception as e:
            logger.error(f"Tool '{tool.name}' raised exception: {type(e).__name__}: {e}")
            return e

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
