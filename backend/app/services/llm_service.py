import os
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
from google import genai

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
        self.api_key = os.getenv("GEMINI_API_KEY")

        if self.api_key:
            # Remove GOOGLE_API_KEY to avoid the "both keys set" warning
            os.environ.pop("GOOGLE_API_KEY", None)
            self.client = genai.Client(api_key=self.api_key)
            self.model_name = "gemini-2.5-pro"
            self._enabled = True
            logger.info("Gemini LLM Service initialized.")
        else:
            self._enabled = False
            logger.warning("GEMINI_API_KEY not found. LLM features disabled.")

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

You must analyze:
- What ML tasks the user needs (primary AND secondary)
- What data modality/format is implied
- How specific or broad the query is (affects search strategy)
- What potential risks or limitations exist in finding this data

CRITICAL: The user's query may contain typos, misspellings, or be a fragmented sentence. You must autocorrect the spelling and reconstruct the query into a logical, professionally formulated sentence before generating the plan.

Your output must contain ALL of the following fields:

1. "domain" — one of: nlp, cv, tabular, time-series, audio, multimodal, general
2. "modality" — data type: "image", "text", "tabular", "audio", "video", "point-cloud", "multi-modal", "time-series"
3. "primary_tasks" — list of the MAIN ML tasks (e.g. "segmentation", "classification")
4. "secondary_tasks" — list of RELATED or IMPLIED tasks (e.g. query says "segmentation" → secondary could include "localization", "detection")
5. "search_query" — the BEST single short phrase (2-4 keywords) to search on Kaggle/HuggingFace.
   RULES: Keep the core DATA SUBJECT + ML TASK. Drop method names, adjectives, filler.
6. "keyword_variants" — list of 4-6 alternative search terms for broader coverage.
7. "semantic_context" — ONE rich sentence describing the IDEAL dataset (modality, format, labels, domain, use-case).
8. "objective" — ONE sentence summarizing the search goal.
9. "constraints" — object with:
   - "required_annotations": list of annotation types needed (e.g. ["pixel-level masks", "class labels"])
   - "preferred_format": e.g. "image + mask pairs", "CSV", "JSON"
   - "min_quality": "high", "medium", or "any"
10. "uncertainty_level" — "low", "medium", or "high" — how confident the agent is about finding good results.
11. "strategy_reasoning" — 1-2 sentences explaining the search strategy decision.
12. "tool_priority" — ordered list of platforms: ["huggingface", "kaggle", "arxiv", "github", "opendataportal"].
13. "tool_rationale" — brief reason for tool ordering (1 sentence).
14. "risk_notes" — list of 1-2 potential issues (e.g. "Medical datasets may be gated", "Niche topic — expect fewer results").
15. "corrected_query" — The user's formally autocorrected and reconstructed query.
16. "anti_keywords" — list of 4-8 terms that are semantically adjacent to the query but indicate IRRELEVANT datasets.
   PURPOSE: These terms will be used to penalize datasets that match them. For example, if the user wants "customer reviews", anti_keywords should include terms like "chatbot", "support ticket", "dialogue", "QA" — things that contain the word "customer" but are NOT review datasets.
   RULES: Think about what OTHER types of datasets share keywords with the desired dataset but are fundamentally different in purpose.

EXAMPLES:

Query: "Explainable Multi-Task Learning for Retinal Image Segmentation and Pathology Classification"
Output:
{{
  "domain": "cv",
  "modality": "image",
  "primary_tasks": ["segmentation", "classification"],
  "secondary_tasks": ["localization", "grading"],
  "search_query": "retinal fundus segmentation",
  "keyword_variants": ["diabetic retinopathy", "fundus photography", "optic disc segmentation", "eye disease dataset", "retinal OCT"],
  "semantic_context": "Medical image dataset of retinal fundus photographs with pixel-level segmentation masks and multi-class disease labels.",
  "objective": "Find retinal image datasets with both segmentation masks and disease classification labels for multi-task learning.",
  "constraints": {{
    "required_annotations": ["pixel-level masks", "disease class labels"],
    "preferred_format": "image + mask pairs with CSV labels",
    "min_quality": "high"
  }},
  "uncertainty_level": "medium",
  "strategy_reasoning": "Medical imaging datasets are niche. Expanding with 5 keyword variants and prioritizing HuggingFace + Kaggle for annotated datasets.",
  "tool_priority": ["huggingface", "kaggle", "arxiv", "github", "opendataportal"],
  "tool_rationale": "HuggingFace has the best medical imaging datasets; Kaggle has competitions with annotations; ArXiv for benchmark references.",
  "risk_notes": ["Medical imaging datasets may require ethics approval or gated access", "Multi-task datasets (seg + class) are rare — may need to combine separate datasets"],
  "corrected_query": "Explainable multi-task learning for retinal image segmentation and pathology classification.",
  "anti_keywords": ["natural image", "scene recognition", "face detection", "self-driving", "satellite", "remote sensing"]
}}

Now analyze:
Query: "{query}"

Return ONLY valid JSON (no markdown, no explanation).
"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )

            text = response.text.strip()

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

            # Normalize: merge primary_tasks into tasks for backward compat
            primary = parsed.get("primary_tasks", [])
            secondary = parsed.get("secondary_tasks", [])
            parsed["tasks"] = primary  # backward compat with orchestrator

            # Ensure all required fields with fallbacks
            if not parsed.get("search_query"):
                parsed["search_query"] = " ".join(query.split()[:4])
            if not parsed.get("keyword_variants"):
                parsed["keyword_variants"] = [parsed["search_query"]]
            if not parsed.get("semantic_context"):
                parsed["semantic_context"] = query
            if not parsed.get("domain"):
                parsed["domain"] = "general"
            if not parsed.get("modality"):
                parsed["modality"] = "unknown"
            if not primary:
                parsed["primary_tasks"] = []
            if not secondary:
                parsed["secondary_tasks"] = []
            if not parsed.get("objective"):
                parsed["objective"] = f"Find datasets relevant to: {query}"
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
                f"primary={parsed['primary_tasks']}, secondary={parsed['secondary_tasks']}, "
                f"uncertainty={parsed['uncertainty_level']}, tools={parsed['tool_priority']}"
            )

            _cache.put("plan", query, parsed)
            return parsed

        except Exception as e:
            logger.error(f"Error in unified parse_and_plan with Gemini: {e}")
            fallback = self._fallback_plan(query)
            _cache.put("plan", query, fallback)
            return fallback

    def _fallback_plan(self, query: str) -> Dict[str, Any]:
        """Deterministic fallback when LLM is disabled or fails."""
        fallback_q = " ".join(query.split()[:4])
        return {
            "domain": "general",
            "modality": "unknown",
            "primary_tasks": [],
            "secondary_tasks": [],
            "tasks": [],
            "search_query": fallback_q,
            "keyword_variants": [fallback_q],
            "semantic_context": query,
            "objective": f"Find datasets relevant to: {query}",
            "constraints": {"required_annotations": [], "preferred_format": "any", "min_quality": "any"},
            "uncertainty_level": "medium",
            "strategy_reasoning": "Using default multi-source search strategy.",
            "tool_priority": ["huggingface", "kaggle", "arxiv", "github", "opendataportal"],
            "tool_rationale": "Default ordering by general relevance.",
            "risk_notes": [],
            "corrected_query": query,
        }

    # ── UNIFIED: Explanation + Summary for top N results ─────────────────────

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
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            text = response.text.strip()
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