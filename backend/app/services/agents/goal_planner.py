"""
Goal Planner Agent (Optimized)
------------------------------
Builds a structured goal plan from the unified LLM output.
This is now fully deterministic — takes the already-parsed LLM response
and enriches it with domain-specific quality thresholds and constraints.

No LLM calls happen here.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ── Domain-specific quality thresholds ────────────────────────────────────────
DOMAIN_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "cv": {
        "min_downloads": 50,
        "preferred_licenses": ["cc-by-4.0", "mit", "apache-2.0", "cc0-1.0"],
        "required_annotation_hints": ["segmentation", "mask", "bounding box", "annotation", "labeled"],
        "known_gaps": "Medical imaging datasets may be gated or require ethics approval.",
    },
    "nlp": {
        "min_downloads": 100,
        "preferred_licenses": ["mit", "apache-2.0", "cc-by-4.0", "cc0-1.0"],
        "required_annotation_hints": ["labeled", "annotated", "sentiment", "NER", "QA"],
        "known_gaps": "Low-resource language datasets are scarce on public platforms.",
    },
    "time-series": {
        "min_downloads": 30,
        "preferred_licenses": ["cc0-1.0", "odc-by", "pddl", "cc-by-4.0"],
        "required_annotation_hints": ["timestamp", "time series", "sequential", "hourly", "daily"],
        "known_gaps": "Real-time industrial sensor data is usually proprietary.",
    },
    "tabular": {
        "min_downloads": 50,
        "preferred_licenses": ["cc0-1.0", "mit", "apache-2.0", "odc-by"],
        "required_annotation_hints": ["csv", "structured", "features", "tabular"],
        "known_gaps": "Government datasets may have usage restrictions or require registration.",
    },
    "audio": {
        "min_downloads": 20,
        "preferred_licenses": ["cc-by-4.0", "mit", "apache-2.0"],
        "required_annotation_hints": ["transcript", "labeled", "ASR", "speech"],
        "known_gaps": "Speech datasets are heavily language-specific.",
    },
    "general": {
        "min_downloads": 10,
        "preferred_licenses": ["mit", "apache-2.0", "cc0-1.0", "cc-by-4.0"],
        "required_annotation_hints": [],
        "known_gaps": "Without a specific domain, result quality may vary.",
    },
}


class GoalPlanner:
    """
    Generates a structured goal plan from the unified LLM parse_and_plan output.
    Deterministic — enriches the LLM output with domain thresholds and constraints.
    """

    def plan(
        self,
        query: str,
        domain: str,
        tasks: List[str],
        search_query: str,
        keyword_variants: List[str],
        semantic_context: str,
        tool_priority: List[str] | None = None,
        objective: str | None = None,
        corrected_query: str | None = None,
    ) -> Dict[str, Any]:
        """
        Returns structured goal plan dict.
        Now accepts optional `tool_priority`, `objective`, and `corrected_query` from the unified LLM call.
        """
        thresholds = DOMAIN_THRESHOLDS.get(domain, DOMAIN_THRESHOLDS["general"])

        # --- Objective (prefer LLM-generated if available) ---
        display_query = corrected_query or query
        if not objective:
            task_str = ", ".join(tasks) if tasks else "general dataset discovery"
            objective = (
                f"Find datasets matching: '{display_query}'. Focus on {domain} domains for {task_str}. "
                f"Core requirement: {semantic_context}"
            )

        # --- Constraints ---
        constraints = {
            "domain": domain,
            "tasks": tasks,
            "preferred_licenses": thresholds["preferred_licenses"],
            "min_quality_signals": {
                "min_downloads": thresholds["min_downloads"],
            },
            "annotation_requirements": thresholds["required_annotation_hints"],
        }

        # --- Success Criteria ---
        success_criteria = {
            "min_candidates_before_ranking": 500,
            "min_semantic_score": 0.30,
            "min_results_to_return": 5,
            "preferred_recency_years": 4,
        }

        # --- Search Strategy (use LLM tool_priority if provided) ---
        ordered_tools = tool_priority or ["kaggle","huggingface", "arxiv", "github", "opendataportal"]

        search_strategy = {
            "primary_query": search_query,
            "keyword_variants": keyword_variants,
            "tool_priority": ordered_tools,
            "approach": (
                f"Start with '{search_query}' across {ordered_tools[:3]}. "
                f"Expand to {len(keyword_variants)} variants to hit 500+ candidates minimum. "
                f"Fallback tools: {ordered_tools[3:] if len(ordered_tools) > 3 else 'none'}."
            ),
        }

        # --- Uncertainty ---
        uncertainty_note = thresholds["known_gaps"]
        if domain == "cv" and any(t in " ".join(tasks or []).lower() for t in ["medical", "retinal", "xray", "mri"]):
            uncertainty_note = (
                "Medical imaging datasets are often gated, ethics-restricted, or require institutional access. "
                "Public alternatives (e.g. Kaggle DR detection, DRIVE, STARE) will be prioritised."
            )

        plan = {
            "objective": objective,
            "constraints": constraints,
            "success_criteria": success_criteria,
            "search_strategy": search_strategy,
            "uncertainty_note": uncertainty_note,
        }

        logger.info(f"Goal Plan → Objective: {objective[:80]}...")
        logger.info(f"Goal Plan → Tool priority: {ordered_tools}")
        return plan


goal_planner = GoalPlanner()
