from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
import traceback
import json
import asyncio
from app.models.schemas import (
    ProjectContext,
    DatasetRankingResponse,
    DatasetMetadata,
    RetrievalPlan,
    FeedbackEvent,
    DatasetDetailResponse
)
from app.services.orchestrator import orchestrator
from app.services.ranking_service import rank_datasets
from app.services.graph_service import graph_service
from app.services.learning_service import learning_ranker
from app.services.preview_service import preview_service
from app.services.auth_service import auth_service
from app.services.llm_service import llm_service
from app.services.agents.goal_planner import goal_planner
from app.services.agents.evaluator import agent_evaluator
from app.services.agents.memory_store import memory_store
from app.config import TOP_K_RESULTS
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Projects"])


def _sse(payload: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/rank/stream")
async def rank_stream(context: ProjectContext, request: Request):
    """
    Optimized SSE streaming endpoint.

    LLM call architecture (2 max, 0 if cached):
      Call 1: parse_and_plan  — unified query parsing + planning
      Call 2: explain_and_summarize — explanation for top 3 results only

    Full response caching: if same query repeats → 0 LLM calls.
    """
    loop = asyncio.get_event_loop()

    async def generate():
        try:
            # ── AUTH ──────────────────────────────────────────────
            auth_service.validate_client(context.client_id, request.client.host)

            # ── CHECK FULL RESPONSE CACHE ─────────────────────────
            cached_response = llm_service.get_cached_final_response(context.query)
            if cached_response is not None:
                logger.info(f"Full response cache HIT for query: '{context.query[:50]}'")
                # Emit stages instantly as completed
                yield _sse({"stage": 0, "text": "Loading cached results..."})
                yield _sse({"stage": 1, "text": "Cached — skipping API search"})
                yield _sse({"stage": 2, "text": "Cached — skipping graph ingestion"})
                yield _sse({"stage": 3, "text": "Cached — skipping ranking"})
                yield _sse({"stage": 4, "text": "Cached — skipping evaluation"})
                if cached_response.get("goal_plan"):
                    yield _sse({"goal_plan": cached_response["goal_plan"]})
                for src, cnt in cached_response.get("source_counts", {}).items():
                    yield _sse({"source": src, "count": cnt})
                yield _sse(cached_response["final_payload"])
                return

            # ── STAGE 0: Unified LLM parse + plan (1 Gemini call) ─
            yield _sse({"stage": 0, "text": "Parsing query intent & building goal plan..."})

            llm_plan = await llm_service.parse_and_plan(context.query)

            effective_domain = context.domain or llm_plan.get("domain", "general")
            effective_tasks = list(set((context.tasks or []) + llm_plan.get("tasks", [])))
            search_query = llm_plan.get("search_query") or " ".join(context.query.split()[:4])
            keyword_variants = llm_plan.get("keyword_variants", [])
            semantic_context = llm_plan.get("semantic_context") or context.query
            tool_priority = llm_plan.get("tool_priority")
            objective = llm_plan.get("objective")
            anti_keywords = llm_plan.get("anti_keywords", [])

            # Goal plan — deterministic enrichment, no extra LLM call
            goal_plan = goal_planner.plan(
                query=context.query,
                domain=effective_domain,
                tasks=effective_tasks,
                search_query=search_query,
                keyword_variants=keyword_variants,
                semantic_context=semantic_context,
                tool_priority=tool_priority,
                objective=objective,
                corrected_query=llm_plan.get("corrected_query", context.query),
            )
            yield _sse({"goal_plan": goal_plan})

            # Emit agent perception (visible reasoning trace for the frontend)
            yield _sse({"agent_perception": {
                "domain": effective_domain,
                "modality": llm_plan.get("modality", "unknown"),
                "primary_tasks": llm_plan.get("primary_tasks", effective_tasks),
                "secondary_tasks": llm_plan.get("secondary_tasks", []),
                "constraints": llm_plan.get("constraints", {}),
                "uncertainty_level": llm_plan.get("uncertainty_level", "medium"),
                "strategy_reasoning": llm_plan.get("strategy_reasoning", ""),
                "tool_rationale": llm_plan.get("tool_rationale", ""),
                "risk_notes": llm_plan.get("risk_notes", []),
            }})

            # ── STAGES 0.5–1: Agent-Driven Discovery ─────────────────
            # The DiscoveryAgent handles paper discovery, query planning,
            # tool selection, iterative exploration, and early stopping.
            # It emits progress events via the `emit` callback.
            async def emit_sse(payload):
                """Bridge: agent calls this to emit SSE events."""
                # We can't yield from inside a callback, so we collect events
                pass  # Events are emitted by the agent's own logging

            yield _sse({"stage": 1, "text": f"Agent starting discovery: '{search_query}'..."})
            retrieval_result = await orchestrator.retrieve(
                query=context.query,
                domain=effective_domain,
                tasks=effective_tasks,
                search_query=search_query,
                keyword_variants=keyword_variants,
                tool_priority=tool_priority,
            )
            candidates = retrieval_result["candidates"]
            agent_memory = retrieval_result.get("agent_memory")

            # Emit agent reasoning trace to frontend
            if agent_memory:
                yield _sse({"agent_reasoning": agent_memory.get_summary()})

            # emit per-source counts so frontend can show them live
            for src, cnt in retrieval_result["source_counts"].items():
                yield _sse({"source": src, "count": cnt})

            if not candidates:
                uncertainty = agent_evaluator.generate_uncertainty_report(
                    goal_plan,
                    {"confidence": 0.0, "quality_label": "weak", "summary": "No candidates found."},
                    retrieval_result["source_counts"],
                )
                final_payload = {
                    "done": True, "datasets": [], "plan": retrieval_result["plan"],
                    "source_counts": retrieval_result["source_counts"],
                    "total_candidates": 0, "errors": retrieval_result["errors"],
                    "status": "No candidates found from any source",
                    "agent_report": {"goal_plan": goal_plan, "uncertainty": uncertainty},
                }
                yield _sse(final_payload)
                # Cache empty result too
                llm_service.cache_final_response(context.query, {
                    "goal_plan": goal_plan,
                    "source_counts": retrieval_result["source_counts"],
                    "final_payload": final_payload,
                })
                return

            # ── STAGE 2: Neo4j graph ingestion ────────────────────
            yield _sse({"stage": 2, "text": f"Ingesting {len(candidates)} candidates into knowledge graph..."})
            await loop.run_in_executor(
                None,
                lambda: graph_service.ingest_candidates(
                    query=context.query,
                    tasks=context.tasks,
                    candidates=candidates,
                )
            )

            # ── STAGE 3: LambdaRank scoring ───────────────────────
            yield _sse({"stage": 3, "text": "Running LightGBM LambdaRank relevance scoring..."})
            ranked_semantic = await loop.run_in_executor(
                None,
                lambda: rank_datasets(
                    query=semantic_context,
                    dataset_candidates=candidates,
                    tasks=effective_tasks,
                    domain=effective_domain,
                    keyword_variants=keyword_variants,
                    anti_keywords=anti_keywords,
                    top_k=40,  # Get top 40 for LLM re-ranking
                )
            )
            
            # Point 10: Deep LLM Re-Ranking (Top 40 -> Top 20)
            yield _sse({"stage": 3.5, "text": "Performing deep agent re-ranking with Gemini..."})
            ranked = await llm_service.rank_with_llm(
                query=context.query,
                candidates=ranked_semantic,
                top_k=25  # Extract top 25 high-quality candidates
            )
            
            # Apply categorization
            all_practical = []
            all_research = []
            for ds in ranked:
                if ds.get("is_paper_seed") or ds.get("paper_source") or ds.get("source", "").lower() == "arxiv":
                    ds["dataset_category"] = "research_benchmark"
                    all_research.append(ds)
                else:
                    ds["dataset_category"] = "practical"
                    all_practical.append(ds)
            
            # Slice according to limits: 15 practical, 5 research (3 ieee, 1 arxiv, 1 s2)
            practical_ranked = all_practical[:15]
            
            research_ranked = []
            ieee_count, arxiv_count, s2_count = 0, 0, 0
            remaining_research = []
            for ds in all_research:
                src = ds.get("paper_source", "arxiv")
                if src == "ieee" and ieee_count < 3:
                    research_ranked.append(ds)
                    ieee_count += 1
                elif src == "arxiv" and arxiv_count < 1:
                    research_ranked.append(ds)
                    arxiv_count += 1
                elif src == "semantic_scholar" and s2_count < 1:
                    research_ranked.append(ds)
                    s2_count += 1
                else:
                    remaining_research.append(ds)
            
            # Fill up to 5 if deficient
            while len(research_ranked) < 5 and remaining_research:
                research_ranked.append(remaining_research.pop(0))
                
            ranked = practical_ranked + research_ranked

            # ── STAGE 4: Evaluation + Explanations (1 Gemini call) ─
            yield _sse({"stage": 4, "text": "Evaluating result quality & generating explanations..."})

            # Deterministic evaluation with self-adjustment (no LLM)
            evaluation = agent_evaluator.evaluate_results(
                context.query, goal_plan, ranked, llm_plan=llm_plan
            )

            # LLM explanation for top 3 only (1 Gemini call, cached)
            explained = await llm_service.explain_and_summarize(
                query=context.query,
                objective=goal_plan.get("objective", context.query),
                ranked_datasets=ranked,
                max_explain=3,
            )

            # Fill remaining datasets with heuristic explanations
            explained = agent_evaluator.heuristic_explain(goal_plan, explained)

            # Deterministic uncertainty report (no LLM)
            uncertainty = agent_evaluator.generate_uncertainty_report(
                goal_plan, evaluation, retrieval_result["source_counts"]
            )

            results = [DatasetMetadata(**ds).model_dump() for ds in explained]
            
            # Map explained metadata back to categorized lists
            # We use ds['id'] to find the explained version
            id_to_explained = {d['id']: d for d in results}
            
            practical_results = [
                id_to_explained[d['id']] 
                for d in practical_ranked if d['id'] in id_to_explained
            ]
            research_results = [
                id_to_explained[d['id']] 
                for d in research_ranked if d['id'] in id_to_explained
            ]

            plan = RetrievalPlan(**retrieval_result["plan"]).model_dump()

            final_payload = {
                "done": True,
                "datasets": results,
                "practical_datasets": practical_results,
                "research_benchmarks": research_results,
                "plan": plan,
                "source_counts": retrieval_result["source_counts"],
                "total_candidates": retrieval_result["total"],
                "errors": retrieval_result["errors"],
                "status": "Success",
                "agent_report": {
                    "goal_plan":  goal_plan,
                    "evaluation": evaluation,
                    "uncertainty": uncertainty,
                    "discovery_summary": agent_memory.get_summary() if agent_memory else None,
                },
            }
            yield _sse(final_payload)

            # Cache the full response for repeat queries
            llm_service.cache_final_response(context.query, {
                "goal_plan": goal_plan,
                "source_counts": retrieval_result["source_counts"],
                "final_payload": final_payload,
            })

            # ── Long-Term Memory: Save session outcome ───────────────
            # We store the outcome (top datasets) to improve future discoveries
            await memory_store.save_session_outcome(
                query=context.query,
                domain=effective_domain,
                tasks=effective_tasks,
                top_datasets=results,
                confidence=evaluation.get("confidence", 0.0)
            )

        except asyncio.CancelledError:
            logger.info("SSE stream cancelled by client/server shutdown.")
        except GeneratorExit:
            pass
        except HTTPException as e:
            yield _sse({"error": e.detail, "status_code": e.status_code})
        except Exception as e:
            logger.error(traceback.format_exc())
            yield _sse({"error": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )




@router.post("/rank", response_model=DatasetRankingResponse)
async def rank_project_datasets(context: ProjectContext, request: Request):
    """
    Non-streaming ranking endpoint (optimized — 2 LLM calls max).
    """
    try:
        # Step 0: Auth & Rate Limiting
        auth_service.validate_client(context.client_id, request.client.host)

        # Step 1: Unified LLM parsing + planning (1 call)
        llm_plan = await llm_service.parse_and_plan(context.query)
        effective_domain = context.domain or llm_plan.get("domain", "general")
        effective_tasks = list(set((context.tasks or []) + llm_plan.get("tasks", [])))
        search_query = llm_plan.get("search_query") or " ".join(context.query.split()[:4])

        # Step 2-3: Multi-source retrieval via orchestrator
        retrieval_result = await orchestrator.retrieve(
            query=context.query,
            domain=effective_domain,
            tasks=effective_tasks,
            search_query=search_query,
            keyword_variants=llm_plan.get("keyword_variants", []),
        )

        candidates = retrieval_result["candidates"]

        if not candidates:
            return DatasetRankingResponse(
                datasets=[],
                plan=RetrievalPlan(**retrieval_result["plan"]),
                source_counts=retrieval_result["source_counts"],
                total_candidates=0,
                errors=retrieval_result["errors"],
                status="No candidates found from any source",
            )

        # Phase 4: Ingest candidates into Neo4j Graph
        graph_service.ingest_candidates(
            query=context.query,
            tasks=context.tasks,
            candidates=candidates
        )

        # Step 4: Rank with Multi-Factor Engine
        ranking_results = rank_datasets(
            query=llm_plan.get("corrected_query", context.query),
            dataset_candidates=candidates,
            tasks=context.tasks,
            domain=effective_domain,
            keyword_variants=llm_plan.get("keyword_variants", []),
            anti_keywords=llm_plan.get("anti_keywords", []),
            dataset_role=llm_plan.get("dataset_role"),
            research_goal=llm_plan.get("research_goal"),
            top_k=TOP_K_RESULTS
        )
        ranked = ranking_results["all"]
        practical_ranked = ranking_results["practical"]
        research_ranked = ranking_results["research_benchmarks"]

        # Step 5: Format response
        results = [DatasetMetadata(**ds) for ds in ranked]
        practical_res = [DatasetMetadata(**ds) for ds in practical_ranked]
        research_res = [DatasetMetadata(**ds) for ds in research_ranked]

        # ── Long-Term Memory: Save session outcome ───────────────
        import asyncio
        asyncio.create_task(memory_store.save_session_outcome(
            query=context.query,
            domain=effective_domain,
            tasks=effective_tasks,
            top_datasets=[d.model_dump() for d in results],
            confidence=0.7 # Default adequate for non-stream for now
        ))

        return DatasetRankingResponse(
            datasets=results,
            practical_datasets=practical_res,
            research_benchmarks=research_res,
            plan=RetrievalPlan(**retrieval_result["plan"]),
            source_counts=retrieval_result["source_counts"],
            total_candidates=retrieval_result["total"],
            errors=retrieval_result["errors"],
            status="Success",
        )

    except HTTPException:
        raise
    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback")
async def submit_feedback(feedback: FeedbackEvent, request: Request):
    """
    Log user interactions with datasets to iteratively train the internal ranker.
    Expects event types: 'click', 'bookmark', or 'download'.
    """
    # Phase 7 Auth
    ip = request.client.host
    client_id = auth_service.ip_to_client_id.get(ip)
    if not client_id:
         raise HTTPException(status_code=403, detail="No client session found for this IP.")

    auth_service.check_rate_limit(client_id, ip)
    
    if feedback.event_type not in ["click", "bookmark", "download"]:
        raise HTTPException(status_code=400, detail="Invalid event type")
    
    learning_ranker.log_feedback(
        query=feedback.query,
        dataset_id=feedback.dataset_id,
        event_type=feedback.event_type,
        features={"semantic": 0.5, "task": 0.5, "quality": 0.5, "license": 0.5, "freshness": 0.5, "graph": 0.1}
    )

    # ── Long-Term Memory: Reinforce successful hits ─────────────
    # This teaches the agent which datasets were actually useful for this query
    import asyncio
    asyncio.create_task(memory_store.record_feedback(
        query=feedback.query,
        dataset_id=feedback.dataset_id,
        event_type=feedback.event_type
    ))

    return {"status": "Feedback recorded", "dataset_id": feedback.dataset_id}

@router.post("/train")
async def trigger_training():
    """
    Triggers the LambdaRank LightGBM model to fine-tune based on accumulated user feedback.
    """
    res = learning_ranker.train_model()
    return {"status": res}

@router.get("/top100")
async def get_top100_datasets():
    """
    Fetches the top 100 datasets (50 HuggingFace, 50 Kaggle) ranked by a weighted community score:
      score = 0.70 × norm(likes) + 0.30 × norm(downloads)

    Strategy:
      1. Fetch top HF datasets (by likes & downloads)
      2. Fetch top Kaggle datasets (by votes & list)
      3. Merge and deduplicate by dataset id within source
      4. Min-max normalise likes and downloads within the ENTIRE pool so the formula works uniformly
      5. Compute composite score, sort descending
      6. Select top 50 from HuggingFace and top 50 from Kaggle
      7. Return combined sorted list
    """
    import httpx
    import asyncio
    import os

    HF_URL = "https://huggingface.co/api/datasets"
    KAGGLE_URL = "https://www.kaggle.com/api/v1/datasets/list"
    POOL_SIZE = 200  # candidates per signal to ensure we find 50 good ones

    def _build_hf_params(sort_field: str) -> dict:
        return {"limit": POOL_SIZE, "full": "true", "sort": sort_field, "direction": -1}

    def _build_kaggle_params(sort_field: str) -> dict:
        return {"page": 1, "pageSize": POOL_SIZE, "sortBy": sort_field}

    def _normalize_hf(ds: dict) -> dict | None:
        ds_id = ds.get("id", "")
        if not ds_id: return None
        desc = (ds.get("description") or (ds.get("cardData") or {}).get("description") or "")
        if not desc or len(desc.strip()) < 20:
            desc = ds_id
        raw_tags = ds.get("tags", [])
        clean_tags = [t.split(":", 1)[1] if ":" in t else t for t in raw_tags]
        clean_tags = [t for t in clean_tags if not t.startswith(("n<", "n>"))]

        card = ds.get("cardData") or {}
        raw_license = card.get("license") or "unknown"
        if isinstance(raw_license, list): raw_license = raw_license[0] if raw_license else "unknown"

        return {
            "id": ds_id,
            "source": "huggingface",
            "description": desc[:500],
            "downloads": max(int(ds.get("downloads") or 0), 0),
            "likes": max(int(ds.get("likes") or 0), 0),
            "url": f"https://huggingface.co/datasets/{ds_id}",
            "license": str(raw_license),
            "last_modified": ds.get("lastModified", ""),
            "tags": clean_tags[:8],
            "similarity_score": 0.0,
        }

    def _normalize_kaggle(ds: dict) -> dict | None:
        ref = ds.get("ref", "")
        if not ref: return None
        desc = ds.get("subtitle") or ds.get("description") or ""
        if not desc or len(desc.strip()) < 20: desc = ref
        return {
            "id": ref,
            "source": "kaggle",
            "description": desc[:500],
            "downloads": max(int(ds.get("downloadCount") or 0), 0),
            "likes": max(int(ds.get("voteCount") or 0), 0),
            "url": f"https://www.kaggle.com/datasets/{ref}",
            "license": str(ds.get("licenseName", "unknown")),
            "last_modified": ds.get("lastUpdated", ""),
            "tags": [t.get("name", "") for t in ds.get("tags", [])][:8],
            "similarity_score": 0.0,
        }

    try:
        hf_likes_data, hf_dl_data, kg_votes_data, kg_dl_data = [], [], [], []
        
        # Determine Kaggle Auth
        kaggle_auth = {}
        token = os.getenv("KAGGLE_API_TOKEN")
        un = os.getenv("KAGGLE_USERNAME")
        key = os.getenv("KAGGLE_KEY")
        if token:
            kaggle_auth = {"headers": {"Authorization": f"Bearer {token}"}}
        elif un and key:
            kaggle_auth = {"auth": (un, key)}

        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = [
                client.get(HF_URL, params=_build_hf_params("likes")),
                client.get(HF_URL, params=_build_hf_params("downloads"))
            ]
            if kaggle_auth: # Only fetch Kaggle if auth is available
                tasks.extend([
                    client.get(KAGGLE_URL, params=_build_kaggle_params("votes"), **kaggle_auth),
                    client.get(KAGGLE_URL, params=_build_kaggle_params("hottest"), **kaggle_auth)
                ])

            res = await asyncio.gather(*tasks, return_exceptions=True)

            if not isinstance(res[0], Exception) and res[0].status_code == 200: hf_likes_data = res[0].json()
            if not isinstance(res[1], Exception) and res[1].status_code == 200: hf_dl_data = res[1].json()
            
            if kaggle_auth and len(res) == 4:
                if not isinstance(res[2], Exception) and res[2].status_code == 200: kg_votes_data = res[2].json()
                if not isinstance(res[3], Exception) and res[3].status_code == 200: kg_dl_data = res[3].json()

        # Merge deduplicate pools
        seen: dict[str, dict] = {}
        for raw in (*hf_likes_data, *hf_dl_data):
            entry = _normalize_hf(raw)
            if entry and entry["id"] not in seen:
                seen[entry["id"]] = entry
                
        for raw in (*kg_votes_data, *kg_dl_data):
            entry = _normalize_kaggle(raw)
            if entry and entry["id"] not in seen:
                seen[entry["id"]] = entry

        pool = list(seen.values())

        # Drop truly noisy entries
        pool = [d for d in pool if d["description"] != d["id"]]

        if not pool:
            return {"datasets": [], "total": 0}

        # Min-max normalise within entire combined pool
        max_likes = max(d["likes"] for d in pool) or 1
        min_likes = min(d["likes"] for d in pool)
        max_dl    = max(d["downloads"] for d in pool) or 1
        min_dl    = min(d["downloads"] for d in pool)
        likes_range = max_likes - min_likes or 1
        dl_range    = max_dl    - min_dl    or 1

        hf_pool, kg_pool = [], []
        for d in pool:
            norm_likes = (d["likes"]     - min_likes) / likes_range
            norm_dl    = (d["downloads"] - min_dl)    / dl_range
            score      = 0.70 * norm_likes + 0.30 * norm_dl
            d["similarity_score"] = round(score, 4)
            
            if d["source"] == "huggingface":
                hf_pool.append(d)
            elif d["source"] == "kaggle":
                kg_pool.append(d)

        # Sort combined pools and select top 50 / 50
        hf_pool.sort(key=lambda d: d["similarity_score"], reverse=True)
        kg_pool.sort(key=lambda d: d["similarity_score"], reverse=True)
        
        top_half_hf = hf_pool[:50]
        # if Kaggle has fewer than 50 or auth was missing, make up for it with HF, or just enforce exact 50
        kg_target = 50
        hf_target = 100 - min(len(kg_pool), kg_target)
        top_kg = kg_pool[:kg_target]
        top_hf = hf_pool[:hf_target]

        final_100 = top_hf + top_kg
        final_100.sort(key=lambda d: d["similarity_score"], reverse=True)

        return {"datasets": final_100, "total": len(final_100)}

    except Exception as e:
        logger.error(f"top100 fetch failed: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch top datasets: {e}")


@router.get("/dataset/{source}/{dataset_id:path}", response_model=DatasetDetailResponse)
async def get_dataset_info(source: str, dataset_id: str):
    """
    Phase 6: Fetch rich metadata and preview for a specific dataset.
    Optimized: No LLM call. Uses the existing description directly.
    """
    # 1. Fetch details and preview
    details = preview_service.get_dataset_details(dataset_id, source)
    
    return DatasetDetailResponse(
        metadata=DatasetMetadata(
            id=dataset_id,
            source=source,
            description=details.get("description", ""),
            url=details["redirect_url"]
        ),
        preview=details["preview"],
        redirect_url=details["redirect_url"],
        size_bytes=details["size_bytes"],
        size_readable=details["size_readable"],
        estimated_download_time=details["estimated_download_time"]
    )


