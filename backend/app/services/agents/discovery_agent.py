"""
Discovery Agent
-----------------
The core autonomous agent loop for dataset discovery.

Architecture:
  perceive → plan → select tool → execute → evaluate → update memory → decide

This replaces the brute-force "run all variants × all tools" approach
with an intelligent, memory-driven iterative exploration.

Key behaviors:
  1. Plans which queries are worth exploring (not all LLM variants)
  2. Selects tools based on domain context (not always all 5)
  3. Evaluates results in-flight (not just post-hoc)
  4. Stops early when confident (not after exhausting all variants)
  5. Expands based on discoveries (adaptive, not static)
"""

import asyncio
import logging
import re
from typing import Dict, List, Any, Optional, Callable, Awaitable

from app.services.agents.agent_memory import AgentMemory
from app.services.retrieval.tool_registry import registry
from app.services.paper_discovery_service import paper_discovery
from app.services.agents.memory_store import memory_store

logger = logging.getLogger(__name__)


# ── Domain → Relevant Tool Subsets ───────────────────────────────────────────
# An agent decides which tools matter, not the user.
DOMAIN_TOOL_MAP: Dict[str, List[str]] = {
    "cv": ["kaggle", "arxiv", "huggingface", "github"],
    "nlp": ["kaggle", "arxiv", "huggingface", "github"],
    "tabular": ["kaggle", "huggingface", "opendataportal"],
    "audio": ["kaggle", "huggingface", "arxiv"],
    "time-series": ["kaggle", "opendataportal", "huggingface"],
    "geospatial": ["opendataportal", "kaggle", "huggingface", "github"],
    "medical": ["arxiv", "huggingface", "kaggle", "github"],
    "multimodal": ["arxiv", "huggingface", "kaggle", "github"],
}

ALL_TOOLS = ["kaggle", "arxiv", "huggingface", "github", "opendataportal"]

# ── Canonical High-Quality Seeds ───────────────────────────────────────────
CANONICAL_SEEDS = {
    "cv": {
        "detection": ["COCO", "KITTI", "Cityscapes", "BDD100K", "Waymo Open", "PASCAL VOC"],
        "segmentation": ["Cityscapes", "COCO", "ADE20K", "Mapillary Vistas", "DeepGlobe"],
        "classification": ["ImageNet-1K", "CIFAR-10", "CIFAR-100", "MNIST", "Places365"],
        "enhancement": ["REDS", "Vimeo-90K", "SIDD", "DND", "LOL dataset"]
    },
    "nlp": {
        "classification": ["IMDB", "SST-2", "AG News", "MNLI"],
        "qa": ["SQuAD", "Natural Questions", "HotpotQA"],
        "summarization": ["CNN/DailyMail", "XSum", "BillSum"]
    }
}

class DiscoveryAgent:
    """
    Autonomous dataset discovery agent.
    Each call to `discover()` creates a fresh AgentMemory and runs
    the iterative exploration loop.
    """

    async def discover(
        self,
        query: str,
        domain: str,
        tasks: List[str],
        modality: str,
        search_query: str,
        keyword_variants: List[str],
        interpretations: Optional[List[str]] = None,
        tool_priority: Optional[List[str]] = None,
        limits: Optional[Dict[str, int]] = None,
        emit: Optional[Callable[[Dict], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        Main agent entry point.

        Args:
            query: Full user query
            domain: Detected domain (cv, nlp, tabular, etc.)
            tasks: Detected ML tasks
            search_query: Primary short keyword phrase
            keyword_variants: LLM-suggested search variants
            tool_priority: Preferred tool ordering
            limits: Per-tool fetch limits
            emit: Optional async callback for SSE progress events

        Returns:
            {
                "candidates": [...],
                "source_counts": {...},
                "total": int,
                "errors": [...],
                "plan": {...},
                "discovery_context": {...},
                "agent_memory": AgentMemory
            }
        """
        memory = AgentMemory(query=query, domain=domain, tasks=tasks)
        
        # ── Step 0: Long-Term Memory (Past Experience) ───────────────────
        try:
            past_hits = await memory_store.get_past_experience(query, domain)
            if past_hits:
                memory.log_reasoning(f"Step 0: Long-Term Memory active. Retrieved {len(past_hits)} past high-confidence results.")
                memory.record_exploration("memory_hit", "memory", past_hits)
            else:
                memory.log_reasoning("Step 0: Long-Term Memory check. No relevant past experiences found.")
        except Exception as e:
            logger.warning(f"LTM retrieval failed (non-fatal): {e}")

        # ── Phase 1: Perception ──────────────────────────────────────────
        memory.log_reasoning(f"Step 1: Input analysis. Query: '{query}'. Classified into domain '{domain}' with tasks {tasks}.")
        memory.log_reasoning(f"Step 1.1: Intent extraction. Extracted primary search query: '{search_query}'. Analyzed {len(keyword_variants)} variants.")

        # ── Phase 2: Paper Discovery (academic seeds) ────────────────────
        discovery_context = {}
        try:
            if emit:
                await emit({"stage": "0.5", "text": "Discovering benchmark datasets from research papers..."})

            paper_metadata = await paper_discovery.discover(search_query)
            if paper_metadata:
                memory.log_reasoning(f"Paper discovery found {len(paper_metadata)} dataset seeds.")
                memory.record_paper_discovery([m["name"] for m in paper_metadata])
                for meta in paper_metadata:
                    discovery_context[meta["name"].lower()] = meta
            else:
                memory.log_reasoning("Paper discovery returned 0 seeds.")
        except Exception as e:
            memory.log_reasoning(f"Paper discovery failed (non-fatal): {e}")

        # ── Phase 3: Intelligent Query Planning ──────────────────────────
        all_targets = [search_query]
        if interpretations:
            all_targets = list(set([search_query] + interpretations))

        planned_queries = []
        for target in all_targets:
            queries = self._plan_queries(target, keyword_variants, discovery_context, memory)
            planned_queries.extend(queries)
            
        # Deduplicate and cap
        seen_p = set()
        unique_p = []
        for q in planned_queries:
            if q.lower() not in seen_p:
                seen_p.add(q.lower())
                unique_p.append(q)
        planned_queries = unique_p[:15]

        memory.log_reasoning(
            f"Step 3: Planning. Multi-hypothesis mode active: {len(all_targets)} targets. "
            f"Total planned queries: {len(planned_queries)}."
        )

        # ── Phase 4: Dynamic Tool Selection ──────────────────────────────
        selected_tools = self._select_tools(domain, tool_priority)
        tools = registry.get_tools_by_names(selected_tools)
        memory.log_reasoning(f"Step 4: Tool Selection. Activated {len(selected_tools)} discovery platforms: {[t.name for t in tools]}.")

        # Point 5: Normalize earlier. MAX_PER_SOURCE = 20
        default_limits = {
            "huggingface": 30, "kaggle": 30, "arxiv": 30,
            "github": 30, "opendataportal": 30
        }
        effective_limits = {**(limits or default_limits)}

        # Build the plan dict for the response
        plan = {
            "tools": selected_tools,
            "limits": effective_limits,
            "reasoning": (
                f"Agent selected {len(selected_tools)} tools for domain '{domain}' and modality '{modality}'. "
                f"Planned {len(planned_queries)} targeted queries across {len(all_targets)} interpretations. "
                f"Paper seeds: {len(discovery_context)}."
            ),
        }

        # ── Phase 5: Iterative Agent Loop ────────────────────────────────
        errors: List[Dict] = []

        # Iteration 1: Primary query across all selected tools
        memory.iteration_count = 1
        if emit:
            await emit({"stage": 1, "text": f"[Iter 1] Searching '{search_query}' across {len(tools)} tools..."})

        primary_results = await self._run_tools(tools, search_query, effective_limits, memory, errors)
        memory.record_exploration(search_query, "all", primary_results)
        memory.log_reasoning(f"Step 5: Initial Retrieval. Primary search found {len(primary_results)} raw results.")

        # Check if we can stop early (User requested total max 50 datasets)
        if memory.get_unique_dataset_count() < 50 and not memory.should_stop():
            # Iteration 2: Parallel execution of planned queries
            memory.iteration_count = 2
            remaining_queries = [q for q in planned_queries if q != search_query and q not in memory.explored_queries]

            if remaining_queries:
                if emit:
                    await emit({"stage": 1, "text": f"[Iter 2] Running {len(remaining_queries)} planned queries in parallel..."})

                # Run in parallel but cap at 8 concurrent queries
                batch = remaining_queries[:8]
                variant_tasks = [
                    self._run_tools(tools, q, effective_limits, memory, errors)
                    for q in batch
                ]
                batch_results = await asyncio.gather(*variant_tasks)
                for q, results in zip(batch, batch_results):
                    memory.record_exploration(q, "all", results)

                memory.log_reasoning(
                    f"Variant batch returned {sum(len(r) for r in batch_results)} results. "
                    f"Total unique: {memory.get_unique_dataset_count()}."
                )

        # Check again — may need adaptive expansion
        if memory.get_unique_dataset_count() < 50 and not memory.should_stop():
            # Iteration 3: Agent-driven expansion based on discoveries
            memory.iteration_count = 3
            expansions = memory.suggest_expansions()

            if expansions:
                if emit:
                    await emit({"stage": 1, "text": f"[Iter 3] Agent expanding: {expansions[:3]}..."})

                memory.log_reasoning(f"Agent expanding with {len(expansions)} discovery-driven queries: {expansions}")

                expansion_tasks = [
                    self._run_tools(tools, q, effective_limits, memory, errors)
                    for q in expansions[:5]
                ]
                expansion_results = await asyncio.gather(*expansion_tasks)
                for q, results in zip(expansions, expansion_results):
                    memory.record_exploration(q, "expansion", results)

                memory.log_reasoning(f"Expansion complete. Total unique: {memory.get_unique_dataset_count()}.")
            else:
                memory.log_reasoning("No expansion suggestions — agent is satisfied with coverage.")

        # ── Phase 6: Heuristic Filtering (Point 4) ───────────────────────
        all_candidates = memory.get_all_candidates()
        
        # Point 4: Heuristic filter to reduce candidates to ~120
        memory.log_reasoning(f"Step 6: Heuristic Filtering. Filtering {len(all_candidates)} candidates down to high-quality results (Modality: {modality}).")
        all_candidates = self._heuristic_filter(all_candidates, query, domain, modality)
        
        # ── Phase 7: Enrich with Paper Context ───────────────────────────
        self._enrich_with_paper_context(all_candidates, discovery_context)

        # ── Phase 7: Compile Source Counts ────────────────────────────────
        source_counts: Dict[str, int] = {}
        for ds in all_candidates:
            src = ds.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        memory.log_reasoning(
            f"Discovery complete. {len(all_candidates)} unique candidates from {len(source_counts)} sources. "
            f"Session confidence: {memory.compute_session_confidence():.0%}."
        )

        return {
            "candidates": all_candidates,
            "plan": plan,
            "source_counts": source_counts,
            "total": len(all_candidates),
            "errors": errors,
            "discovery_context": discovery_context,
            "agent_memory": memory,
        }

    # ── Internal Methods ─────────────────────────────────────────────────────

    def _plan_queries(
        self,
        primary_query: str,
        variants: List[str],
        discovery_context: Dict,
        memory: AgentMemory,
    ) -> List[str]:
        """
        Intelligent query planning instead of brute-force variant execution.

        Strategy:
          1. Always include the primary query
          2. Include paper-discovered dataset names (high value)
          3. Filter out redundant/noisy variants
          4. Cap total queries to avoid API abuse
        """
        # 1. Always include the primary query
        planned = [primary_query]

        # 1.1 Inject Canonical Seeds (Fix 4: Ensure top benchmarks are included)
        domain_seeds = CANONICAL_SEEDS.get(memory.domain, {})
        for task in memory.tasks:
            for seed in domain_seeds.get(task, []):
                seed_query = f"{seed} dataset"
                if seed_query not in planned:
                    planned.append(seed_query)
                    memory.log_reasoning(f"Injected canonical seed for {task}: '{seed}'")

        # 2. Paper seeds are HIGH VALUE — always include them
        paper_seeds = [meta["seed"] for meta in discovery_context.values()]
        planned.extend(paper_seeds)

        # Filter LLM variants: remove duplicates, very short, or very similar to primary
        primary_tokens = set(primary_query.lower().split())
        for variant in variants:
            if variant in planned or variant == primary_query:
                continue

            variant_tokens = set(variant.lower().split())

            # Skip if variant is essentially the same as primary
            overlap = len(primary_tokens & variant_tokens) / max(len(primary_tokens | variant_tokens), 1)
            if overlap > 0.8:
                continue

            # Skip very short variants (likely noise)
            if len(variant.split()) < 2:
                continue

            planned.append(variant)

        # Deduplicate and cap
        seen = set()
        unique_planned = []
        for q in planned:
            q_key = q.lower().strip()
            if q_key not in seen:
                seen.add(q_key)
                unique_planned.append(q)

        memory.log_reasoning(
            f"Query plan: {len(unique_planned)} queries from "
            f"{len(paper_seeds)} paper seeds + {len(variants)} LLM variants. "
            f"Filtered out {len(variants) - (len(unique_planned) - len(paper_seeds) - 1)} redundant queries."
        )

        return unique_planned[:12]  # Hard cap at 12 search queries

    def _select_tools(
        self, domain: str, tool_priority: Optional[List[str]] = None
    ) -> List[str]:
        """
        Context-aware tool selection.
        An agent decides which tools are relevant, not the user.
        """
        if tool_priority:
            # User/LLM specified priority — respect it but validate
            available = registry.list_names()
            return [t for t in tool_priority if t in available]

        # Domain-driven selection
        domain_key = domain.lower() if domain else "general"
        selected = DOMAIN_TOOL_MAP.get(domain_key, ALL_TOOLS)

        # Validate against registered tools
        available = registry.list_names()
        return [t for t in selected if t in available]

    async def _run_tools(
        self,
        tools: list,
        query: str,
        limits: Dict[str, int],
        memory: AgentMemory,
        errors: List[Dict],
    ) -> List[Dict]:
        """Run all selected tools for a single query in parallel."""
        coros = [
            self._safe_search(tool, query, limits.get(tool.name, 10))
            for tool in tools
        ]
        tool_results = await asyncio.gather(*coros)

        all_results = []
        for tool, res in zip(tools, tool_results):
            if isinstance(res, Exception):
                logger.warning(f"Tool '{tool.name}' / '{query[:40]}' failed: {res}")
                errors.append({"tool": tool.name, "query": query[:50], "error": str(res)})
            elif res:
                logger.info(f"Tool '{tool.name}' / '{query[:40]}': {len(res)} results")
                all_results.extend(res)
        return all_results

    @staticmethod
    async def _safe_search(tool, query: str, limit: int):
        """Run a tool's search with exception handling."""
        try:
            return await tool.search(query, limit)
        except Exception as e:
            logger.error(f"Tool '{tool.name}' raised: {type(e).__name__}: {e}")
            return e

    def _heuristic_filter(self, candidates: List[Dict], query: str, domain: str, modality: str = "any") -> List[Dict]:
        """
        Point 4: Heuristic filtering to reduce candidates before heavy ranking.
        Filters based on basic keyword score, description length, and modality mismatch.
        """
        if not candidates:
            return []

        # Modality signal words for quick rejection (Fix 2 & 5)
        NEG_SIGNALS = {
            "image": ["audio", "speech", "waveform", "acoustic", "text corpus", "nlp task"],
            "audio": ["image", "vision", "video", "pixel", "frame", "text corpus"],
            "tabular": ["image", "vision", "audio", "speech", "waveform", "unstructured"]
        }
        bad_words = NEG_SIGNALS.get(modality, [])

        q_words = set(re.findall(r'\w+', query.lower()))
        scored = []
        for ds in candidates:
            desc = (ds.get("description") or "").lower()
            name = (ds.get("id") or "").lower()
            tags = [t.lower() for t in ds.get("tags", [])]
            ds_text = f"{name} {desc} {' '.join(tags)}".lower()
            ds_words = set(re.findall(r'\w+', ds_text))
            
            # Strict Modality Filter
            if modality != "any" and any(w in ds_text for w in bad_words):
                # Small exception: if 'multimodal' or 'vision' or 'cv' is in tags, keep it
                if not any(v in tags for v in ["multimodal", "vision", "cv", "image"]):
                    continue

            # Length filter: very short descriptions are usually low quality
            if len(desc) < 40 and not ds.get("is_paper_seed"):
                continue

            # Simple word overlap score
            overlap = len(q_words & ds_words)
            
            # Quality signals
            desc_len = len(desc)
            is_labeled = 1.0 if any(kw in ds_text for kw in ["labels", "labeled", "annotations", "bbox", "mask"]) else 0.5
            
            score = (overlap * 2) + (desc_len / 500) + (is_labeled * 10)
            
            # Boost canonical or user-requested matches
            if any(w in name for w in q_words):
                score += 5

            scored.append((score, ds))
            
        # Re-sort and take top 120
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ds for score, ds in scored[:120]]

    @staticmethod
    def _enrich_with_paper_context(candidates: List[Dict], discovery_context: Dict):
        """Enrich candidates with paper discovery metadata."""
        for ds in candidates:
            ds_id_lower = ds.get("id", "").lower()
            ds.setdefault("dataset_category", "practical")

            for name_lower, meta in discovery_context.items():
                if name_lower in ds_id_lower:
                    ds["is_paper_seed"] = True
                    ds["dataset_category"] = "research_benchmark"
                    ds["paper_purpose"] = meta["purpose"]
                    ds["paper_context"] = meta["context"]
                    ds["paper_modality"] = meta["modality"]
                    ds["paper_title"] = meta["paper_title"]
                    ds["paper_url"] = meta["paper_url"]
                    ds["paper_source"] = meta.get("paper_source", "arxiv")
                    ds["year"] = meta["year"]
                    ds["citations"] = meta["citations"]
                    ds["dataset_size"] = meta.get("dataset_size")
                    ds["annotation_type"] = meta.get("annotation_type")

                    if meta["purpose"] == "benchmark":
                        ds["tags"] = list(set(ds.get("tags", []) + ["benchmark"]))
                        ds["benchmark_task"] = meta["purpose"]
                    break  # first match wins


# Module singleton
discovery_agent = DiscoveryAgent()
