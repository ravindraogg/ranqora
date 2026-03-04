"""
Agent Evaluator
---------------
Post-retrieval intelligence layer (optimized — NO LLM calls):

1. Self-Evaluation:  Heuristic confidence scoring (deterministic).
2. Explanation Engine: Heuristic per-dataset justification (fallback only,
                       primary explanations come from llm_service.explain_and_summarize).
3. Uncertainty Awareness: Surface system confidence + honest gaps.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class AgentEvaluator:
    """
    Evaluates ranked results using deterministic heuristics only.
    LLM-based explanations have been moved to llm_service.explain_and_summarize()
    to consolidate all Gemini calls and enable caching.
    """

    # ── 1. Self-Evaluation (deterministic — no LLM) ───────────────────────────

    def evaluate_results(
        self,
        query: str,
        goal_plan: Dict[str, Any],
        ranked_datasets: List[Dict[str, Any]],
        llm_plan: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Evaluate ranked results against the goal plan.
        Now includes self-adjustment: agent reasoning about result quality.

        Returns:
          {
            "confidence": float (0-1),
            "quality_label": "strong" | "adequate" | "weak",
            "should_expand": bool,
            "expansion_hints": [str],
            "summary": str,
            "self_adjustment": [str]    ← NEW: autonomous reasoning messages
          }
        """
        if not ranked_datasets:
            return {
                "confidence": 0.0,
                "quality_label": "weak",
                "should_expand": True,
                "expansion_hints": self._expansion_hints(goal_plan, []),
                "summary": "No datasets found. Try broader keywords or different sources.",
                "self_adjustment": ["No matching datasets found. Recommending broader search terms."],
            }

        top_scores = [ds.get("similarity_score", 0) for ds in ranked_datasets[:5]]
        avg_score = sum(top_scores) / len(top_scores) if top_scores else 0
        best_score = max(top_scores) if top_scores else 0
        n = len(ranked_datasets)

        # Heuristic confidence
        count_factor = min(n / 7, 1.0)          # 7 results = ideal
        score_factor = min(best_score * 1.4, 1.0)  # scale up scores a bit
        confidence = round((0.5 * score_factor) + (0.3 * avg_score) + (0.2 * count_factor), 3)

        # ── Source diversity penalty ──
        # If top results all from same source → overconfident
        top_sources = [ds.get("source", "unknown") for ds in ranked_datasets[:5]]
        unique_sources = len(set(top_sources))
        if unique_sources == 1 and len(top_sources) >= 3:
            confidence = round(confidence * 0.85, 3)

        if confidence >= 0.65:
            quality_label = "strong"
        elif confidence >= 0.42:
            quality_label = "adequate"
        else:
            quality_label = "weak"

        should_expand = quality_label == "weak" and n < 5
        expansion_hints = self._expansion_hints(goal_plan, ranked_datasets) if should_expand else []

        summary = self._build_summary(n, quality_label, confidence, goal_plan)

        # ── Self-Adjustment: autonomous reasoning about result quality ────
        self_adjustment = self._self_adjust(
            ranked_datasets, goal_plan, llm_plan or {}, quality_label, confidence
        )

        return {
            "confidence": confidence,
            "quality_label": quality_label,
            "should_expand": should_expand,
            "expansion_hints": expansion_hints,
            "summary": summary,
            "self_adjustment": self_adjustment,
        }

    def _expansion_hints(self, goal_plan: Dict, datasets: List[Dict]) -> List[str]:
        """Suggests refined queries when results are poor."""
        hints = []
        strategy = goal_plan.get("search_strategy", {})
        variants = strategy.get("keyword_variants", [])
        if variants:
            hints.append(f"Try broader variant: '{variants[0]}'")
        constraints = goal_plan.get("constraints", {})
        tasks = constraints.get("tasks", [])
        if tasks:
            hints.append(f"Relax task filter — search only domain without task: '{constraints.get('domain', '')}'")
        hints.append("Expand to ArXiv for benchmark/research datasets.")
        return hints[:3]

    def _build_summary(
        self, n: int, quality: str, confidence: float, goal_plan: Dict
    ) -> str:
        pct = int(confidence * 100)
        labels = {
            "strong": f"Found {n} strong matches (confidence {pct}%).",
            "adequate": f"Found {n} relevant datasets (confidence {pct}%). Results are adequate but not ideal.",
            "weak": f"Found only {n} datasets with low confidence ({pct}%). Consider refining your query.",
        }
        return labels.get(quality, f"{n} datasets found.")

    def _self_adjust(
        self,
        ranked_datasets: List[Dict],
        goal_plan: Dict,
        llm_plan: Dict,
        quality_label: str,
        confidence: float,
    ) -> List[str]:
        """
        Self-Adjustment Layer: generates autonomous reasoning messages
        about how well results satisfy the user's intent.
        This is what makes the system behave like an agent, not just a search engine.
        """
        messages = []

        # Extract task info
        primary_tasks = llm_plan.get("primary_tasks", [])
        all_tasks = primary_tasks or goal_plan.get("constraints", {}).get("tasks", [])
        uncertainty = llm_plan.get("uncertainty_level", "medium")

        if not ranked_datasets:
            return messages

        # ── 1. Task Coverage Analysis ─────────────────────────────────────
        # Check if top results actually contain the requested tasks
        if all_tasks and len(all_tasks) > 1:
            top5_text = " ".join(
                f"{ds.get('id', '')} {ds.get('description', '')[:100]} {' '.join(ds.get('tags', []))}"
                for ds in ranked_datasets[:5]
            ).lower()

            covered = [t for t in all_tasks if t.lower() in top5_text]
            missing = [t for t in all_tasks if t.lower() not in top5_text]

            if missing and covered:
                missing_str = " + ".join(missing)
                covered_str = " + ".join(covered)
                messages.append(
                    f"Multi-task coverage: {covered_str} datasets found. "
                    f"{missing_str} datasets are limited — expanding to include {missing_str}-only results."
                )
            elif not covered:
                messages.append(
                    f"None of the top results directly match tasks: {', '.join(all_tasks)}. "
                    f"Results are based on domain relevance."
                )
        elif all_tasks and len(all_tasks) == 1:
            task = all_tasks[0].lower()
            top3_text = " ".join(
                f"{ds.get('id', '')} {' '.join(ds.get('tags', []))}"
                for ds in ranked_datasets[:3]
            ).lower()
            if task not in top3_text:
                messages.append(
                    f"Top results may not explicitly contain '{all_tasks[0]}' data. "
                    f"They are ranked by semantic similarity to your overall query."
                )

        # ── 2. Source Diversity Analysis ──────────────────────────────────
        sources = [ds.get("source", "unknown") for ds in ranked_datasets]
        unique_sources = set(sources)
        if len(unique_sources) == 1:
            messages.append(
                f"All results from {sources[0]} only. Consider searching other platforms for broader coverage."
            )
        elif len(unique_sources) >= 3:
            messages.append(
                f"Results sourced from {len(unique_sources)} platforms: {', '.join(sorted(unique_sources))}."
            )

        # ── 3. Quality Assessment ────────────────────────────────────────
        if quality_label == "weak":
            messages.append(
                "Result quality is below threshold. The agent recommends refining your query "
                "or trying more specific terminology."
            )
        elif quality_label == "strong" and confidence >= 0.70:
            messages.append(
                "High-confidence results. Strong semantic and task alignment detected."
            )

        # ── 4. Uncertainty-aware messaging ───────────────────────────────
        if uncertainty == "high":
            messages.append(
                "This is a niche or specialized topic. Fewer results are expected. "
                "Consider checking gated repositories or domain-specific platforms."
            )

        return messages[:4]  # Cap at 4 messages

    # ── 2. Heuristic Explanation (fallback, no LLM) ───────────────────────────

    def heuristic_explain(
        self, goal_plan: Dict, datasets: List[Dict]
    ) -> List[Dict]:
        """Rule-based explanations when LLM explanations are unavailable."""
        result = []
        for ds in datasets:
            ds_copy = dict(ds)
            if "explanation" not in ds_copy:
                ds_copy["explanation"] = self._single_heuristic(ds, goal_plan)
            result.append(ds_copy)
        return result

    def _single_heuristic(self, ds: Dict, goal_plan: Dict) -> Dict:
        score = ds.get("similarity_score", 0)
        tasks = goal_plan.get("constraints", {}).get("tasks", [])
        tags = ds.get("tags", [])
        license_id = ds.get("license", "unknown")
        preferred = goal_plan.get("constraints", {}).get("preferred_licenses", [])

        # Why relevant
        matched_tags = [t for t in tags if any(task.lower() in t.lower() for task in tasks)]
        if matched_tags:
            why = f"Contains tags matching task requirements: {', '.join(matched_tags[:3])}."
        elif score > 0.5:
            why = "High semantic similarity to your project description."
        else:
            why = f"Retrieved from {ds.get('source', 'unknown')} based on keyword match."

        # License note
        if license_id in preferred:
            license_note = f"{license_id} — fully compatible with your use case."
        elif license_id == "unknown":
            license_note = "License unknown — verify before use."
        else:
            license_note = f"{license_id} — check restrictions for your use case."

        # Tradeoff
        downloads = ds.get("downloads", 0)
        if downloads > 10000:
            tradeoff = "Large community adoption suggests reliability, but may be general-purpose."
        elif downloads > 500:
            tradeoff = "Moderate adoption; good balance of specificity and community validation."
        else:
            tradeoff = "Niche dataset — likely more specific to your domain but less validated."

        confidence = "high" if score > 0.60 else ("medium" if score > 0.40 else "low")

        return {
            "why_relevant": why,
            "license_note": license_note,
            "tradeoff": tradeoff,
            "confidence": confidence,
        }

    # ── 3. Uncertainty Awareness (deterministic) ──────────────────────────────

    def generate_uncertainty_report(
        self,
        goal_plan: Dict[str, Any],
        evaluation: Dict[str, Any],
        source_counts: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        Honest uncertainty report attached to the final response.
        """
        gaps = []
        uncertainty_note = goal_plan.get("uncertainty_note", "")
        if uncertainty_note:
            gaps.append(uncertainty_note)

        # Dead sources
        dead_sources = [src for src, cnt in source_counts.items() if cnt == 0]
        if dead_sources:
            gaps.append(f"No results from: {', '.join(dead_sources)} — these sources may not index this domain well.")

        # Low count
        total = sum(source_counts.values())
        if total < 10:
            gaps.append("Fewer than 10 candidates found — consider broadening your query or domain.")

        quality = evaluation.get("quality_label", "adequate")
        confidence = evaluation.get("confidence", 0.5)

        if quality == "weak":
            overall = (
                f"Low confidence ({int(confidence*100)}%). "
                "The system found limited matching datasets. "
                "Results shown are the best available but may not be ideal."
            )
        elif quality == "adequate":
            overall = (
                f"Moderate confidence ({int(confidence*100)}%). "
                "Results are relevant but the ideal dataset may exist in restricted repositories."
            )
        else:
            overall = (
                f"High confidence ({int(confidence*100)}%). "
                "Strong matches found across multiple sources."
            )

        return {
            "overall": overall,
            "confidence": confidence,
            "quality_label": quality,
            "known_gaps": gaps,
            "suggestion": evaluation.get("summary", ""),
        }


# Module-level singleton
agent_evaluator = AgentEvaluator()
