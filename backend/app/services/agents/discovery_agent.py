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

import logging
import re
import asyncio
from typing import List, Dict, Any, Optional, Callable, Awaitable, Sequence, Union, Tuple, Set
from app.services.agents.agent_memory import AgentMemory
from app.services.retrieval.tool_registry import registry
from app.services.paper_discovery_service import paper_discovery
from app.services.agents.memory_store import memory_store
from app.services.embedding_service import get_embedding
from app.services.graph_service import graph_service

logger = logging.getLogger(__name__)


# ── Domain → Relevant Tool Subsets ───────────────────────────────────────────
# An agent decides which tools matter, not the user.
DOMAIN_TOOL_MAP: Dict[str, List[str]] = {
    "cv": ["kaggle", "arxiv", "huggingface"],
    "nlp": ["kaggle", "arxiv", "huggingface"],
    "tabular": ["kaggle", "huggingface", "opendataportal"],
    "audio": ["kaggle", "huggingface", "arxiv"],
    "time-series": ["kaggle", "opendataportal", "huggingface"],
    "geospatial": ["opendataportal", "kaggle", "huggingface"],
    "medical": ["arxiv", "huggingface", "kaggle"],
    "multimodal": ["arxiv", "huggingface", "kaggle"],
}

ALL_TOOLS = ["kaggle", "arxiv", "huggingface", "opendataportal"]

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
        request = None, # Fix: Track disconnection
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
        
        async def check_abort():
            if request and await request.is_disconnected():
                logger.info(f"Discovery Agent: User disconnected. Aborting session for '{query[:40]}'")
                raise asyncio.CancelledError()

        # ── Step 0: Long-Term Memory (Past Experience) ───────────────────
        await check_abort()
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
        await check_abort()
        memory.log_reasoning(f"Step 1: Input analysis. Query: '{query}'. Classified into domain '{domain}' with tasks {tasks}.")
        memory.log_reasoning(f"Step 1.1: Intent extraction. Extracted primary search query: '{search_query}'. Analyzed {len(keyword_variants)} variants.")

        # ── Phase 2: Paper Discovery (academic seeds) ────────────────────
        discovery_context = {}
        try:
            if emit:
                await emit({"stage": "0.5", "text": "Discovering benchmark datasets from research papers..."})

            # Fix: Pass request to track abortion
            paper_metadata = await paper_discovery.discover(search_query, request=request)
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
        await check_abort()
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
        planned_queries = unique_p[:10]

        # ── Phase 3.1: Embedding-Based Expansion (Fix 1) ──────────────────
        memory.log_reasoning("Step 3.1: Embedding-based expansion starting...")
        embedding_seeds = await self._expand_via_embeddings(search_query, memory)
        if embedding_seeds:
            planned_queries.extend(embedding_seeds)
            # Re-deduplicate
            seen_p = set()
            unique_p = []
            for q in planned_queries:
                if q.lower() not in seen_p:
                    seen_p.add(q.lower())
                    unique_p.append(q)
            planned_queries = unique_p[:10]

        memory.log_reasoning(
            f"Step 3: Planning. Multi-hypothesis mode active: {len(all_targets)} targets. "
            f"Total planned queries: {len(planned_queries)} (incl. {len(embedding_seeds)} embedding seeds)."
        )

        # ── Phase 4: Dynamic Tool Selection ──────────────────────────────
        selected_tools = self._select_tools(domain, tool_priority)
        tools = registry.get_tools_by_names(selected_tools)
        memory.log_reasoning(f"Step 4: Tool Selection. Activated {len(selected_tools)} discovery platforms: {[t.name for t in tools]}.")

        # Point 5: Normalize earlier. MAX_PER_SOURCE = 100 (Increased per user)
        default_limits = {
            "huggingface": 70, "kaggle": 70, "arxiv": 50,
            "opendataportal": 70
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

        # Check if we can stop early (User requested higher total max)
        await check_abort()
        if memory.get_unique_dataset_count() < 100 and not memory.should_stop():
            # Iteration 2: Parallel execution of planned queries
            memory.iteration_count = 2
            remaining_queries = [q for q in planned_queries if q != search_query and q not in memory.explored_queries]

            await check_abort()

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
        await check_abort()
        if memory.get_unique_dataset_count() < 50 and not memory.should_stop():
            # Iteration 3: Agent-driven expansion based on discoveries
            memory.iteration_count = 3
            expansions = memory.suggest_expansions()

            if expansions:
                await check_abort()
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
        await check_abort()
        all_candidates = memory.get_all_candidates()
        
        # Phase 6.1: Injection & Deduplication (Fix 3)
        memory.log_reasoning(f"Step 6.1: Injecting {len(discovery_context)} paper seeds into candidates...")
        self._inject_paper_benchmarks(all_candidates, discovery_context)
        
        memory.log_reasoning(f"Step 6.2: Deduplicating {len(all_candidates)} candidates across platforms...")
        all_candidates = self._deduplicate_candidates(all_candidates)

        # Point 4: Heuristic filter to reduce candidates to ~120
        memory.log_reasoning(f"Step 6.2: Heuristic Filtering. Filtering {len(all_candidates)} candidates down to high-quality results.")
        all_candidates = self._heuristic_filter(all_candidates, query, domain, modality)
        
        # Phase 6.3: Dataset Integrity Check (Fix 10)
        memory.log_reasoning("Step 6.3: Dataset Integrity Check (modality, size, annotations)...")
        all_candidates = self._dataset_integrity_check(all_candidates, modality, tasks)

        # ── Phase 7: Enrich with Paper Context ───────────────────────────
        await check_abort()
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

        # Fix 8: Constant Dataset-Specific Expansions
        dataset_expansions = [
            f"{primary_query} dataset",
            f"{primary_query} benchmark",
            f"{primary_query} corpus"
        ]
        for q in dataset_expansions:
            if q not in planned:
                planned.append(q)

        # Vague query fallback expansion (Fix 5)
        if len(planned) < 7: # Increased threshold for fallback
            vague_expansions = [
                f"{primary_query} training data",
                f"{primary_query} open dataset",
                f"{primary_query} collection"
            ]
            for q in vague_expansions:
                if q not in planned:
                    planned.append(q)

        # Deduplicate and cap
        seen = set()
        unique_planned = []
        for q in planned:
            q_key = q.lower().strip()
            if q_key not in seen:
                seen.add(q_key)
                unique_planned.append(q)

        memory.log_reasoning(
            f"Query plan finalized: {len(unique_planned)} queries. "
            f"(ArXiv seeds: {len(paper_seeds)}, LLM variants: {len(variants)}, Vague Fallback: {len(planned) < 9})"
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
        # Fix 5: Adaptive Timeouts (8s for intensive sources, 5s for others)
        coros = []
        for tool in tools:
            # Fix: Increased ArXiv timeout to 8s per user, shared with Kaggle/HF
            to_val = 8.0 if tool.name in ["kaggle", "huggingface", "arxiv"] else 5.0
            coros.append(
                asyncio.wait_for(
                    self._safe_search(tool, query, limits.get(tool.name, 10)),
                    timeout=to_val
                )
            )
        
        # Use return_exceptions=True to not fail the whole batch if one times out
        tool_results = await asyncio.gather(*coros, return_exceptions=True)

        all_results = []
        for tool, res in zip(tools, tool_results):
            if isinstance(res, asyncio.TimeoutError):
                safe_to = 8.0 if tool.name in ["kaggle", "huggingface"] else 5.0
                logger.warning(f"Tool '{tool.name}' / '{query[:40]}' timed out ({safe_to}s).")
                errors.append({"tool": tool.name, "query": query[:50], "error": "timeout"})
            elif isinstance(res, Exception):
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

    async def _expand_via_embeddings(self, query: str, memory: AgentMemory) -> List[str]:
        """
        Fix 1: Add Embedding-Based Query Expansion.
        Vector search -> nearest neighbors -> extract keywords.
        """
        try:
            # 1. Embed query
            emb = get_embedding(query)
            
            # 2. Vector search in graph (Fix 1: Using specialized TITLE index)
            neighbors = graph_service.vector_search(emb.tolist(), top_k=25, index_name='dataset_title_vector_index')
            if not neighbors:
                # Fallback to general index if title index is empty
                neighbors = graph_service.vector_search(emb.tolist(), top_k=25, index_name='dataset_vector_index')
            
            if not neighbors:
                return []
            
            # 3. Extract keywords/names from neighbors
            new_queries = []
            for n in neighbors:
                name = n.get("id", "")
                if name and len(name) > 3:
                    # Clean dataset name for search
                    clean_name = re.sub(r'[^a-zA-Z0-9\s]', ' ', name).strip()
                    if clean_name and clean_name not in new_queries:
                        new_queries.append(f"{clean_name} dataset")
            
            memory.log_reasoning(f"Embedding expansion found {len(new_queries)} semantic neighbors for seeds.")
            return new_queries[:5]  # Take top 5 unique neighbor seeds
        except Exception as e:
            logger.warning(f"Embedding expansion failed: {e}")
            return []

    def _deduplicate_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """
        Fix 3: Add Dataset Deduplication.
        Uses fingerprint = normalize(name + description).
        Groups and merges metadata.
        """
        if not candidates:
            return []
            
        unique_map: Dict[str, Dict] = {}
        
        for ds in candidates:
            # Create a fingerprint: normalize name and a snippet of description
            name = (ds.get("id") or "").lower()
            desc = (ds.get("description") or "")[:100].lower()
            # Remove noise like 'dataset', 'data'
            norm_id = re.sub(r'[^a-z0-9]', '', name)
            norm_desc = re.sub(r'[^a-z0-9]', '', desc)
            
            fingerprint = f"{norm_id}_{norm_desc[:30]}"
            # Also check for partial ID match if names are long
            id_prefix = norm_id[:12]
            
            # Check if this fingerprint or the ID prefix is already known
            match_found = False
            for existing_fp, existing_ds in unique_map.items():
                existing_norm_id = re.sub(r'[^a-z0-9]', '', existing_ds.get("id", "").lower())
                # If IDs are very similar OR fingerprint matches
                if (norm_id in existing_norm_id or existing_norm_id in norm_id) and (len(norm_id) > 5):
                    match_found = True
                    fingerprint = existing_fp
                    break
                if fingerprint == existing_fp:
                    match_found = True
                    break

            if match_found:
                # Merge: take highest downloads, cumulative tags
                existing = unique_map[fingerprint]
                existing["downloads"] = max(existing.get("downloads", 0), ds.get("downloads", 0))
                existing["likes"] = max(existing.get("likes", 0), ds.get("likes", 0))
                existing["tags"] = list(set(existing.get("tags", []) + ds.get("tags", [])))
                # Keep original source but note secondary ones
                if "other_sources" not in existing:
                    existing["other_sources"] = []
                if ds["source"] != existing["source"]:
                    existing["other_sources"].append(ds["source"])
            else:
                unique_map[fingerprint] = dict(ds)
                
        return list(unique_map.values())

    def _dataset_integrity_check(self, candidates: List[Dict], modality: str, tasks: List[str]) -> List[Dict]:
        """
        Fix 10: Final Dataset Integrity Check.
        Validates: modality, minimum size, and annotation presence.
        """
        if not candidates:
            return []
            
        checked = []
        for ds in candidates:
            desc = (ds.get("description") or "").lower()
            name = (ds.get("id") or "").lower()
            tags = [t.lower() for t in ds.get("tags", [])]
            text = f"{name} {desc} {' '.join(tags)}"
            
            # Rule 1: Dataset Size Validation (Fix 4)
            # Some platforms provide downloads/likes, but 'size' is often in description
            # If we see "10 samples" or "5 images", reject.
            small_match = re.search(r"(\d+)\s+(samples?|images?|files?|sentences?)", desc)
            if small_match:
                count = int(small_match.group(1))
                if count < 100: # Fix 4: minimum_samples >= 100
                    continue
            
            # Rule 2: Modality Integrity (Fix 10)
            # If modality is audio, ensure audio keywords exist.
            if modality == "audio" and not any(w in text for w in ["audio", "speech", "voice", "sound", "wav", "mp3", "asr", "spoken", "digit", "recognition"]):
                continue
            if modality == "image" and not any(w in text for w in ["image", "vision", "picture", "photo", "jpg", "png", "pixel"]):
                continue
            
            # Rule 3: Annotation Check (Fix 10)
            # If a task is classification or segmentation, check for label keywords
            if any(t in ["classification", "segmentation", "detection"] for t in tasks):
                if not any(w in text for w in ["label", "annotation", "mask", "bbox", "ground truth", "dataset"]):
                    # If it's a paper seed, we're more lenient as description might be sparse
                    if not ds.get("is_paper_seed"):
                        continue
            
            checked.append(ds)
            
        return checked

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

    def _inject_paper_benchmarks(self, candidates: List[Dict], discovery_context: Dict):
        """Inject paper-discovered seeds as standalone candidates if not found elsewhere."""
        existing_ids = {c.get("id", "").lower() for c in candidates}
        existing_names = {c.get("id", "").split("/")[-1].lower() for c in candidates}
        
        injected = []
        for name, meta in discovery_context.items():
            name_lower = name.lower()
            # Check if name is already represented in results (as ID or tail of ID)
            if name_lower in existing_ids or name_lower in existing_names:
                continue
            
            # Create a virtual candidate
            ds = {
                "id": meta["name"],
                "source": meta.get("paper_source", "arxiv"), # Default to arxiv if missing, but we fixed service
                "description": f"Research Dataset mentioned in: {meta['paper_title']}. Context: {meta['context']}",
                "downloads": 100 + (meta["citations"] * 5), # Synthetic popularity
                "likes": 10 + meta["citations"],
                "url": meta["paper_url"],
                "tags": ["research", "benchmark"],
                "is_paper_seed": True,
                "dataset_category": "research_benchmark",
                "paper_purpose": meta["purpose"],
                "paper_context": meta["context"],
                "paper_modality": meta["modality"],
                "paper_title": meta["paper_title"],
                "paper_url": meta["paper_url"],
                "paper_source": meta.get("paper_source", "arxiv"),
                "year": meta["year"],
                "citations": meta["citations"],
                "dataset_size": meta.get("dataset_size"),
                "annotation_type": meta.get("annotation_type")
            }
            injected.append(ds)
        
        candidates.extend(injected)

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
