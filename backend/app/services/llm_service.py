import os
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
from google import genai
from huggingface_hub import InferenceClient

logger = logging.getLogger(__name__)


class LLMCache:
    """Simple in-memory LRU cache for LLM responses, keyed by normalized query."""

    def __init__(self, max_size: int = 256):
        self._cache: Dict[str, Any] = {}
        self._order: list = []
        self._max_size = max_size

    @staticmethod
    def _normalize(query: str) -> str:
        return query.lower().strip()

    @staticmethod
    def _key(prefix: str, text: str) -> str:
        normalized = LLMCache._normalize(text)
        return hashlib.sha256(f"{prefix}:{normalized}".encode()).hexdigest()

    def get(self, prefix: str, query: str) -> Optional[Any]:
        k = self._key(prefix, query)
        if k in self._cache:
            # Move to end (most recent)
            self._order.remove(k)
            self._order.append(k)
            logger.info(f"LLM cache HIT for prefix='{prefix}'")
            return self._cache[k]
        return None

    def put(self, prefix: str, query: str, value: Any):
        k = self._key(prefix, query)
        if k in self._cache:
            self._order.remove(k)
        elif len(self._cache) >= self._max_size:
            evict = self._order.pop(0)
            del self._cache[evict]
        self._cache[k] = value
        self._order.append(k)


# Module-level cache singleton
_cache = LLMCache(max_size=256)


class LLMService:
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.hf_token = os.getenv("HF_TOKEN")
        
        self.hf_model = "Qwen/Qwen2.5-7B-Instruct"
        self.hf_client = None
        
        if self.hf_token:
            self.hf_client = InferenceClient(api_key=self.hf_token)
            logger.info(f"HuggingFace LLM Service initialized with {self.hf_model}.")

        if self.gemini_api_key:
            # Remove GOOGLE_API_KEY to avoid the "both keys set" warning
            os.environ.pop("GOOGLE_API_KEY", None)
            self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            self.gemini_model = "gemini-2.0-flash"
            self._gemini_enabled = True
            logger.info("Gemini LLM Service initialized.")
        else:
            self._gemini_enabled = False
            logger.warning("GEMINI_API_KEY not found. Gemini mode disabled.")

        self._enabled = self._gemini_enabled or (self.hf_client is not None)

    async def _generate_content_with_fallback(self, prompt: str) -> str:
        """Try Gemini first, then fallback to HF Qwen."""
        if self._gemini_enabled:
            try:
                # Standard generate call
                response = self.gemini_client.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                logger.error(f"Gemini generation failed: {e}. Falling back to HF...")

        if self.hf_client:
            try:
                completion = self.hf_client.chat.completions.create(
                    model=self.hf_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2048
                )
                return completion.choices[0].message.content.strip()
            except Exception as hf_e:
                logger.error(f"HF / Qwen generation failed: {hf_e}")
                raise hf_e

        raise Exception("No LLM service enabled (neither Gemini nor HF).")

    # ── UNIFIED: Parse + Plan in ONE structured call ─────────────────────────

    async def parse_and_plan(self, query: str) -> Dict[str, Any]:
        """
        Single Gemini call that produces:
          - domain, tasks, search_query, keyword_variants, semantic_context
          - objective, tool_priority

        Replaces the old separate parse_user_query + goal_planner.plan calls.
        If cache hits → 0 LLM calls.
        """
        # Check cache first
        cached = _cache.get("plan", query)
        if cached is not None:
            return cached

        if not self._enabled:
            fallback = self._fallback_plan(query)
            _cache.put("plan", query, fallback)
            return fallback

        prompt = f"""
You are an autonomous AI dataset discovery agent. Given a user query, perform deep intent analysis and return a STRICT JSON response.

Your perception module must classify queries into three levels:

Level 1: Dataset Type (modality)
- Options: "image", "text", "tabular", "audio", "video", "point-cloud", "multi-modal", "time-series", "unknown"
- CRITICAL: If the query does not specify modality, set this to "unknown". Do NOT guess vision.

Level 2: Dataset Role
- Options: "benchmark", "training", "evaluation", "synthetic", "research", "general"
- Purpose: Does the user need a standard evaluation benchmark or just general training data?

Level 3: Research Goal
- This is the core semantic objective (e.g., "robustness", "generalization", "fairness", "classification", "segmentation").

You must also analyze:
- What potential risks or limitations exist in finding this data
- Spelling/Correction: Reconstruct the query into a logical, professionally formulated sentence.

Your output must contain ALL of the following fields:

1. "domain" - one of: nlp, cv, remote_sensing, tabular, time-series, audio, multimodal, general
2. "modality" - From Level 1.
3. "dataset_role" - From Level 2.
4. "research_goal" - From Level 3.
5. "primary_tasks" - list of the MAIN ML tasks (e.g. "segmentation", "classification")
6. "secondary_tasks" - list of RELATED or IMPLIED tasks.
7. "search_query" - the BEST single short phrase (2-4 keywords) to search. Drop method names, adjectives, filler.
8. "keyword_variants" - list of 4-6 alternative search terms. CRITICAL: Extract and combine keywords, do NOT just truncate the sentence. (e.g. "satellite flood dataset", "remote sensing flood segmentation", "flood detection satellite imagery" instead of "Enhancing Satellite Imagery for").
9. "semantic_context" - ONE rich sentence describing the IDEAL dataset (modality, format, labels, domain, role).
10. "objective" - ONE sentence summarizing the search goal.
11. "constraints" - object with:
   - "required_annotations": list of annotation types needed.
   - "preferred_format": e.g. "image + mask pairs", "CSV", "JSON"
   - "min_quality": "high", "medium", or "any"
12. "uncertainty_level" - "low", "medium", or "high". 
13. "interpretations" - list of 2-3 specific interpretations if uncertainty is > low (e.g. for "anomalies in data streams" -> ["network intrusion detection", "financial fraud detection"]).
14. "strategy_reasoning" - 1-2 sentences explaining the search strategy decision.
15. "tool_priority" - ordered list: ["arxiv", "kaggle", "huggingface", "github", "opendataportal"].
16. "tool_rationale" - brief reason for tool ordering (1 sentence).
17. "risk_notes" - list of 1-2 potential issues.
18. "corrected_query" - The user's formally corrected query.
19. "anti_keywords" - list of 4-8 terms that indicate IRRELEVANT datasets (e.g. ["tutorial", "course", "blog", "survey"]). NEVER include "benchmark" or "evaluation".

EXAMPLE for query: "Improving the Accuracy and Resilience of Machine Learning Models"
{{
  "domain": "general",
  "modality": "unknown",
  "dataset_role": "benchmark",
  "research_goal": "robustness evaluation",
  "primary_tasks": ["classification", "robustness testing"],
  "secondary_tasks": ["generalization"],
  "search_query": "robustness benchmarks",
  "keyword_variants": ["model resilience", "out-of-distribution evaluation", "adversarial robustness", "benchmark datasets"],
  "semantic_context": "Evaluative benchmark datasets used for testing machine learning model resilience and robustness across various domains.",
  "objective": "Identify standard benchmark datasets specifically designed for evaluating model robustness and resilience.",
  "corrected_query": "Improving the accuracy and resilience of machine learning models.",
  "tool_priority": ["arxiv", "kaggle", "huggingface", "github", "opendataportal"],
  "tool_rationale": "Benchmarks are pioneered in research papers (ArXiv) and competitions (Kaggle)."
}}

Now analyze:
Query: "{query}"

Return ONLY valid JSON (no markdown, no explanation).
"""

        try:
            text = await self._generate_content_with_fallback(prompt)

            # Strip markdown code fences if present
            if "```" in text:
                parts = text.split("```")
                text = parts[1].strip()
                if text.startswith("json"):
                    text = text[4:].strip()

            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            text = text[json_start:json_end]

            parsed = json.loads(text)
        except Exception as e:
            logger.error(f"Error in unified parse_and_plan with LLM: {e}")
            parsed = self._fallback_plan(query)

        # ── Apply Post-Processing Heuristics (Always run, even for fallback) ──
        
        # Normalize: merge primary_tasks into tasks for backward compat
        dataset_role = parsed.get("dataset_role", "general")
        research_goal = parsed.get("research_goal", "")
        primary = parsed.get("primary_tasks", [])
        secondary = parsed.get("secondary_tasks", [])
        parsed["tasks"] = primary
        
        # ── Point 3: Domain Detection Heuristics ──
        REMOTE_SENSING_KEYWORDS = {
            "sentinel", "sar", "landsat", "flood", "water segmentation", "remote sensing", "satellite", "aerial",
            "modis", "planet", "goes", "hsi", "msi", "lulc"
        }
        query_lower = query.lower()
        if any(kw in query_lower for kw in REMOTE_SENSING_KEYWORDS):
            if parsed.get("domain") in ["general", "unknown", None]:
                parsed["domain"] = "remote_sensing"
            if parsed.get("modality") in ["unknown", "general", None]:
                parsed["modality"] = "image"
            if not any("segmentation" in str(t).lower() for t in primary):
                primary.append("segmentation")
            if not any("detection" in str(t).lower() or "segmentation" in str(t).lower() for t in primary) and "flood" in query_lower:
                primary.append("flood detection")
            parsed["primary_tasks"] = primary
            parsed["tasks"] = primary

        # ── Fix 1: Modality Inference for Streams ──
        STREAM_KEYWORDS = {
            "stream", "data stream", "real-time", "temporal", "time series", "time-series", "sequential", "sensor"
        }
        if any(kw in query_lower for kw in STREAM_KEYWORDS):
            if parsed.get("modality") in ["unknown", "general", "any", None]:
                parsed["modality"] = "time-series"

        # Ensure all required fields with fallbacks
        if not parsed.get("search_query"):
            parsed["search_query"] = self._smart_extract_query(query)
        if not parsed.get("keyword_variants"):
            parsed["keyword_variants"] = [parsed["search_query"]]
        if not parsed.get("semantic_context"):
            parsed["semantic_context"] = query
        if not parsed.get("domain"):
            parsed["domain"] = "general"
        if not parsed.get("modality"):
            parsed["modality"] = "any"
            
        # ── Vague Query Support: Multi-Hypothesis Generation (Step 3) ──
        if parsed.get("uncertainty_level") != "low" and not parsed.get("interpretations"):
            # Simple heuristic if LLM missed it
            parsed["interpretations"] = [parsed["search_query"]]
        if not parsed.get("dataset_role"):
            parsed["dataset_role"] = "general"
        if not parsed.get("research_goal"):
            parsed["research_goal"] = ""
        if not primary:
            parsed["primary_tasks"] = []
        if not secondary:
            parsed["secondary_tasks"] = []
        if not parsed.get("objective"):
            parsed["objective"] = f"Find datasets relevant to: {query[:100]}..."
        if not parsed.get("tool_priority"):
            parsed["tool_priority"] = ["huggingface", "kaggle", "arxiv", "github", "opendataportal"]
        if not parsed.get("constraints"):
            parsed["constraints"] = {"required_annotations": [], "preferred_format": "any", "min_quality": "any"}
        if not parsed.get("uncertainty_level"):
            parsed["uncertainty_level"] = "medium"
        if not parsed.get("strategy_reasoning"):
            parsed["strategy_reasoning"] = "Using default multi-source search strategy."
        if not parsed.get("tool_rationale"):
            parsed["tool_rationale"] = "Default ordering by general relevance."
        if not parsed.get("risk_notes"):
            parsed["risk_notes"] = []
        if not parsed.get("corrected_query"):
            parsed["corrected_query"] = query
        if not parsed.get("anti_keywords"):
            parsed["anti_keywords"] = []

        logger.info(
            f"Agent Perception → domain={parsed['domain']}, modality={parsed['modality']}, "
            f"primary={parsed['primary_tasks']}, uncertainty={parsed['uncertainty_level']}"
        )

        _cache.put("plan", query, parsed)
        return parsed

    def _smart_extract_query(self, query: str) -> str:
        """Helper to extract a reasonable search query without LLM."""
        # Remove common filler
        stop_words = {"the", "a", "an", "this", "project", "aims", "to", "build", "system", "that", "in", "and", "of", "for", "with"}
        words = [w for w in re.findall(r'\w+', query.lower()) if w not in stop_words]
        
        # Priority keywords to keep
        priority = {"satellite", "imagery", "flood", "detection", "segmentation", "remote", "sensing", "landsat", "sentinel"}
        found_priority = [w for w in words if w in priority]
        
        if found_priority:
            return " ".join(found_priority[:4])
        return " ".join(words[:4])

    def _fallback_plan(self, query: str) -> Dict[str, Any]:
        """Deterministic fallback when LLM is disabled or fails."""
        fallback_q = self._smart_extract_query(query)
        return {
            "domain": "general",
            "modality": "unknown",
            "dataset_role": "general",
            "research_goal": "",
            "primary_tasks": [],
            "secondary_tasks": [],
            "tasks": [],
            "search_query": fallback_q,
            "keyword_variants": [fallback_q],
            "semantic_context": query,
            "objective": f"Find datasets relevant to: {query[:100]}...",
            "constraints": {"required_annotations": [], "preferred_format": "any", "min_quality": "any"},
            "uncertainty_level": "medium",
            "strategy_reasoning": "Using default multi-source search strategy (LLM limited).",
            "tool_priority": ["huggingface", "kaggle", "arxiv", "github", "opendataportal"],
            "tool_rationale": "Default ordering by general relevance.",
            "risk_notes": ["LLM capacity exceeded, results may be broader."],
            "corrected_query": query,
        }

    # ── UNIFIED: Explanation + Summary for top N results ─────────────────────

    async def rank_with_llm(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Point 10: LLM Ranking Layer.
        Takes the top ~40 semantic matches and uses LLM to select and rank the best top_k.
        """
        if not self._enabled or not candidates or len(candidates) < 3:
            return candidates[:top_k]

        # Prepare tiny summaries for the LLM
        summaries = []
        for i, ds in enumerate(candidates[:40]):  # Cap at 40
            summaries.append(
                f"{i+1}. ID={ds.get('id')} | Description={ds.get('description', '')[:200]} "
                f"| Tags={ds.get('tags', [])[:3]}"
            )

        prompt = f"""
You are an expert ML dataset curator. Re-rank the following datasets based on the user query.
Query: {query}

Datasets:
{chr(10).join(summaries)}

Select the TOP {top_k} BEST datasets and return their IDs in priority order.
Return ONLY valid JSON: {{"rank_order": ["id1", "id2", ...]}}
"""
        try:
            text = await self._generate_content_with_fallback(prompt)
            if "```" in text:
                text = text.split("```")[1].strip()
                if text.startswith("json"):
                    text = text[4:].strip()

            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            text = text[json_start:json_end]

            result = json.loads(text)
            rank_order = result.get("rank_order", [])

            # Create a map for fast lookup
            ds_map = {ds["id"]: ds for ds in candidates}
            
            ranked = []
            for ds_id in rank_order:
                if ds_id in ds_map:
                    ranked.append(ds_map[ds_id])
            
            # Fill the rest from the original list if LLM returned fewer than top_k
            remaining = [ds for ds in candidates if ds["id"] not in rank_order]
            ranked.extend(remaining)

            return ranked[:top_k]

        except Exception as e:
            logger.warning(f"LLM ranking failed: {e}")
            return candidates[:top_k]

    async def explain_and_summarize(
        self,
        query: str,
        objective: str,
        ranked_datasets: List[Dict[str, Any]],
        max_explain: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Single Gemini call that generates per-dataset explanations AND
        a concise summary — only for the top `max_explain` results.
        Remaining datasets get heuristic explanations.

        If cache hits → 0 LLM calls.
        """
        if not ranked_datasets:
            return []

        # Build a cache key from query + top dataset IDs
        ds_ids = "|".join(ds.get("id", "") for ds in ranked_datasets[:max_explain])
        cache_key = f"{query}||{ds_ids}"
        cached = _cache.get("explain", cache_key)

        if cached is not None:
            # Merge cached explanations into dataset dicts
            return self._merge_explanations(ranked_datasets, cached, max_explain)

        if not self._enabled:
            return ranked_datasets  # No LLM, datasets already have no explanation

        # Build prompt for top N only
        top_n = ranked_datasets[:max_explain]
        dataset_summaries = []
        for i, ds in enumerate(top_n):
            dataset_summaries.append(
                f"{i+1}. ID={ds.get('id')} | Source={ds.get('source')} "
                f"| Tags={ds.get('tags', [])[:4]} | Score={ds.get('similarity_score', 0):.2f} "
                f"| License={ds.get('license', 'unknown')} | Downloads={ds.get('downloads', 0)}"
            )

        prompt = f"""
You are a dataset curation expert. Given a user objective and the top ranked datasets,
generate a structured justification for each AND a brief overall summary.

User Objective: {objective}

Datasets (top {max_explain}):
{chr(10).join(dataset_summaries)}

Return ONLY valid JSON (no markdown) with this exact structure:
{{
  "explanations": [
    {{
      "rank": 1,
      "why_relevant": "one sentence explaining content match",
      "license_note": "short license compatibility comment",
      "tradeoff": "one sentence on size/quality/recency tradeoff",
      "confidence": "high | medium | low"
    }}
  ],
  "summary": "A 1-2 sentence summary of overall result quality for the user"
}}
"""
        try:
            text = await self._generate_content_with_fallback(prompt)
            if "```" in text:
                text = text.split("```")[1].strip()
                if text.startswith("json"):
                    text = text[4:].strip()

            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            text = text[json_start:json_end]

            result = json.loads(text)
            explanations = result.get("explanations", [])

            _cache.put("explain", cache_key, result)
            return self._merge_explanations(ranked_datasets, result, max_explain)

        except Exception as e:
            logger.warning(f"LLM explain_and_summarize failed: {e}")
            return ranked_datasets

    def _merge_explanations(
        self,
        datasets: List[Dict[str, Any]],
        llm_result: Dict[str, Any],
        max_explain: int,
    ) -> List[Dict[str, Any]]:
        """Merge LLM explanations into dataset dicts."""
        explanations = llm_result.get("explanations", [])
        result = []
        for i, ds in enumerate(datasets):
            ds_copy = dict(ds)
            if i < len(explanations) and i < max_explain:
                ds_copy["explanation"] = explanations[i]
            result.append(ds_copy)
        return result

    # ── Cache utilities ──────────────────────────────────────────────────────

    def get_cached_final_response(self, query: str) -> Optional[Dict[str, Any]]:
        """Check if a complete final response is cached for this query."""
        return _cache.get("final", query)

    def cache_final_response(self, query: str, response: Dict[str, Any]):
        """Store a complete final response in cache."""
        _cache.put("final", query, response)


llm_service = LLMService()