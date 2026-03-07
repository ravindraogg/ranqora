import math
import numpy as np
import threading
import re
import logging
from datetime import datetime, timezone
from dateutil import parser as date_parser
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Any
from app.services.embedding_service import get_embedding, get_embeddings
from app.services.graph_service import graph_service
from app.services.learning_service import learning_ranker
from app.services.dataset_intelligence_service import dataset_intelligence

logger = logging.getLogger(__name__)

# License scoring heuristic (0.0 to 1.0)
LICENSE_SCORES = {
    "mit": 1.0, "apache-2.0": 1.0, "bsd-2-clause": 1.0, "bsd-3-clause": 1.0,
    "cc0-1.0": 1.0, "unlicense": 1.0, "pddl": 1.0, "cc-by-4.0": 0.9,
    "arxiv-paper": 1.0,
    "gpl-3.0": 0.5, "gpl-2.0": 0.5, "cc-by-sa-4.0": 0.6, "cc-by-nc-4.0": 0.4,
    "cc-by-nc-sa-4.0": 0.3, "odc-by": 0.8,
    "unknown": 0.1, "other": 0.1
}

# ── Task Intent Keywords ─────────────────────────────────────────────────────
TASK_INTENT_KEYWORDS: Dict[str, List[str]] = {
    "segmentation":       ["segmentation", "mask", "pixel", "annotation", "labeled", "contour", "boundary", "polygon"],
    "object detection":   ["detection", "bounding box", "bbox", "yolo", "coco", "annotation", "labeled"],
    "classification":     ["classification", "class", "label", "category", "predict"],
    "regression":         ["regression", "continuous", "predict", "numeric"],
    "forecasting":        ["forecast", "time series", "prediction", "temporal", "sequential"],
    "sentiment analysis": ["sentiment", "opinion", "positive", "negative", "review"],
    "ner":                ["ner", "entity", "named entity", "token", "tagging", "iob"],
    "question answering": ["qa", "question", "answer", "squad", "reading comprehension"],
    "speech recognition": ["speech", "asr", "transcript", "audio", "voice", "utterance"],
    "image generation":   ["generation", "gan", "diffusion", "synthetic", "generative"],
    "clustering":         ["clustering", "cluster", "unsupervised", "topic", "grouping", "kmeans"],
    "topic modeling":     ["topic", "lda", "theme", "category", "topic model"],
}

# ── Source Trust Scores (Fix 2) ─────────────────────────────────────────────
# Weights for source reliability. Kaggle/HF are primary, others are secondary/noisy.
SOURCE_TRUST_SCORES: Dict[str, float] = {
    "kaggle":         0.95,
    "huggingface":    0.95,
    "opendataportal": 0.85,
    "github":         0.65,
    "arxiv":          0.45,
    "ieee":           0.50,
    "semanticscholar": 0.45,
}

DATASET_INDICATOR_KEYWORDS = [
    "dataset", "benchmark", "corpus", "data", "annotations",
    "labeled", "training set", "test set", "csv", "parquet"
]

# ── Canonical Research Benchmarks (Boosted) ──────────────────────────────────
CANONICAL_BENCHMARKS = {
    "imagenet", "cifar", "coco", "mnist", "glue", "superglue", "squad",
    "kitti", "cityscapes", "pascal", "voc", "lfw", "celeba", "widerface",
    "imdb", "yelp", "amazon-reviews", "movielens", "netflix", "wmt",
    "lsun", "fashion-mnist", "svhn", "stl-10", "cub-200", "wilds", "imagenet-c"
}

# ── Title noise tokens to remove before embedding ───────────────────────────
TITLE_NOISE_TOKENS = {
    "dataset", "data", "ml", "training", "collection", "v1", "v2", "v3",
    "final", "clean", "cleaned", "processed", "raw", "full", "complete",
    "version", "updated", "new", "latest", "original",
}


def _clean_title_for_embedding(title: str) -> str:
    """Remove noise tokens from dataset title before embedding."""
    parts = re.split(r'[-_/\s]+', title.lower())
    cleaned = [p for p in parts if p and p not in TITLE_NOISE_TOKENS and len(p) > 1]
    return " ".join(cleaned) if cleaned else title.lower()


def _task_intent_bonus(query: str, tasks: List[str], ds: Dict) -> float:
    """
    Additive multi-task intent scoring. Zero embedding cost.
    Returns additive points: 0.0 to ~0.25.
    """
    if not tasks:
        return 0.0

    query_lower = query.lower()
    ds_text = " ".join([
        ds.get("id", ""),
        ds.get("description", "")[:300],
        " ".join(ds.get("tags", []))
    ]).lower()

    bonus = 0.0
    tasks_matched = 0

    for task in tasks:
        task_lower = task.lower()
        intent_keys = TASK_INTENT_KEYWORDS.get(task_lower, [task_lower])

        kw_matches = sum(1 for kw in intent_keys if kw in ds_text)

        if task_lower in ds_text:
            bonus += 0.05
            tasks_matched += 1
        elif kw_matches >= 1:
            bonus += 0.03
            tasks_matched += 1

        if kw_matches >= 3:
            bonus += 0.05
        elif kw_matches >= 2:
            bonus += 0.03

    if len(tasks) > 1 and tasks_matched >= len(tasks):
        bonus += 0.10
    elif len(tasks) > 1 and tasks_matched >= 2:
        bonus += 0.05

    return min(bonus, 0.10)  # Capped to prevent dominating ranking


def _source_penalty(ds: Dict) -> float:
    """
    Penalize non-dataset repositories intelligently.
    Also penalize untrusted sources (not Kaggle/HuggingFace).
    """
    source = ds.get("source", "").lower()
    ds_text = " ".join([
        ds.get("id", ""),
        ds.get("description", "")[:300],
        " ".join(ds.get("tags", []))
    ]).lower()

    # ── GitHub: detect actual datasets ──
    if source == "github":
        dataset_signals = [
            "dataset", "data files", "csv", "parquet",
            "download", "annotations", "benchmark"
        ]
        code_signals = [
            "app", "web app", "flask", "react",
            "model", "classifier", "implementation",
            "system", "using", "built with"
        ]
        has_dataset_signal = any(k in ds_text for k in dataset_signals)
        has_code_signal = any(k in ds_text for k in code_signals)

        if has_dataset_signal and not has_code_signal:
            return 0.9   # likely dataset repo but still untrusted source
        if has_code_signal and not has_dataset_signal:
            return 0.6   # mostly code project
        return 0.75  # ambiguous

    # ── ArXiv: penalize unless dataset provided ──
    if source == "arxiv":
        if "dataset" in ds_text or "benchmark" in ds_text:
            return 0.9
        return 0.7

    # ── OpenDataPortal: slightly less trusted ──
    if source == "opendataportal":
        return 0.9

    # ── Kaggle & HuggingFace: fully trusted ──
    return 1.0
def _is_real_dataset(item: Dict) -> bool:
    """
    Fix 7: Stronger Dataset Signal Filter.
    Checks description and name for core dataset markers.
    """
    desc = (item.get("description") or "").lower()
    name = (item.get("id") or "").lower()
    tags = " ".join(item.get("tags", [])).lower()
    text = f"{name} {desc} {tags}"

    dataset_keywords = [
        "dataset", "corpus", "benchmark", "speech commands", 
        "mnist", "fsdd", "data set", "collection", "labeled",
        "ground truth", "annotations", "cvpr", "voxceleb", "librispeech"
    ]
    
    # Negative signals (mostly code/framework projects)
    code_keywords = ["flask", "web app", "django", "implementation of", "pytorch model", "classifier script"]

    has_data = any(k in text for k in dataset_keywords)
    has_code_only = any(k in name for k in code_keywords) and not has_data

    if has_code_only:
        return False
        
    return has_data or len(desc) > 100 # If desc is rich, give benefit of doubt

def _benchmark_score(ds: Dict) -> float:
    """Boost datasets that are identified as benchmarks."""
    score = 0.0
    ds_id = ds.get("id", "").lower()
    description = ds.get("description", "").lower()
    
    # +15 if dataset introduced in paper discovery
    if ds.get("is_paper_seed") or ds.get("paper_context"):
        score += 0.15
        
    # +20 if dataset contains "benchmark" or "standard"
    if "benchmark" in description or "benchmark" in ds_id or "standard" in description:
        score += 0.20
        
    # +40 if in canonical list
    ds_id_clean = re.sub(r'[^a-z0-9]', '-', ds_id)
    if any(cb in ds_id_clean for cb in CANONICAL_BENCHMARKS):
        score += 0.40
        
    return min(score, 1.0)


def _annotation_score(ds: Dict) -> float:
    """Point 10: Annotation Quality Score.
    Detects presence of specific annotation keywords (masks, boxes, labels).
    """
    score = 0.0
    name = (ds.get("id") or "").lower()
    desc = (ds.get("description") or "").lower()
    tags = " ".join(ds.get("tags", [])).lower()
    ds_text = f"{name} {desc} {tags}"
    
    # Strong signals (Fix 3: Annotation awareness)
    BBOX_KEYWORDS = ["bbox", "bounding box", "bounding-box", "yolo", "coco format", "pascal voc"]
    MASK_KEYWORDS = ["mask", "segmentation", "pixel-level", "polygon", "pixel-wise", "pixelwise"]
    LABEL_KEYWORDS = ["labeled", "labels", "annotations", "ground truth", "annotated"]
    
    if any(kw in ds_text for kw in BBOX_KEYWORDS):
        score += 0.50
    if any(kw in ds_text for kw in MASK_KEYWORDS):
        score += 0.40
    if any(kw in ds_text for kw in LABEL_KEYWORDS):
        score += 0.30
        
    return min(score, 1.0)


def _keyword_overlap_score(query_words: set, ds: Dict) -> float:
    """Fast keyword overlap with sqrt normalization for long queries."""
    ds_text = " ".join([
        ds.get("id", ""),
        ds.get("description", "")[:200],
        " ".join(ds.get("tags", []))
    ]).lower()
    ds_words = set(re.findall(r'\w+', ds_text))
    if not query_words or not ds_words:
        return 0.0
    overlap = len(query_words.intersection(ds_words))
    return overlap / math.sqrt(len(query_words) * len(ds_words))


def _anti_keyword_penalty(
    ds: Dict,
    anti_keywords: List[str],
    constraint_terms: List[str],
) -> float:
    """
    Signal-ratio based anti-keyword penalty.
    
    Instead of hard-dropping candidates, calculate:
      positive_hits = count of constraint_terms found
      negative_hits = count of anti_keywords found
    
    If negative_hits > positive_hits → penalty 0.75
    If negative_hits > 0 but <= positive_hits → no penalty
    If negative_hits == 0 → no penalty
    """
    if not anti_keywords:
        return 1.0

    ds_text = f"{ds.get('id','')} {ds.get('description','')} {' '.join(ds.get('tags',[]))}".lower()

    positive_hits = sum(1 for term in constraint_terms if term in ds_text)
    negative_hits = sum(1 for term in anti_keywords if term in ds_text)

    if negative_hits > positive_hits:
        return 0.75
    return 1.0


def _prefilter_candidates(
    query: str,
    candidates: List[Dict[str, Any]],
    max_for_embedding: int = 80,
    min_per_source: int = 12,
) -> List[Dict[str, Any]]:
    """
    Fast keyword-based pre-filter (Stage 1.5).
    
    Uses adaptive sizing: min(80, max(40, count * 0.12))
    """
    # Adaptive limit based on candidate count
    adaptive_limit = min(max_for_embedding, max(40, int(len(candidates) * 0.12)))
    
    if len(candidates) <= adaptive_limit:
        return candidates
    
    max_for_embedding = adaptive_limit

    query_words = set(re.findall(r'\w+', query.lower()))

    scored = []
    for ds in candidates:
        kw_score = _keyword_overlap_score(query_words, ds)
        downloads = ds.get("downloads", 0)
        quality_boost = min(np.log1p(downloads) / np.log1p(100_000), 1.0) * 0.1
        
        # Fast title match bonus
        title = ds.get("id", "").lower()
        title_hits = sum(1 for w in query_words if w in title)
        title_bonus = min(title_hits * 0.05, 0.15)
        
        # Fast tag match bonus
        tags_text = " ".join(ds.get("tags", [])).lower()
        tag_hits = sum(1 for w in query_words if w in tags_text)
        tag_bonus = min(tag_hits * 0.05, 0.15)
        
        total = kw_score + quality_boost + title_bonus + tag_bonus
        scored.append((total, ds))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Phase 1: Ensure minimum representation per source
    source_buckets: Dict[str, List] = {}
    for score, ds in scored:
        src = ds.get("source", "unknown")
        if src not in source_buckets:
            source_buckets[src] = []
        source_buckets[src].append((score, ds))

    selected_ids = set()
    selected = []

    for src, bucket in source_buckets.items():
        for score, ds in bucket[:min_per_source]:
            ds_id = ds.get("id", "")
            if ds_id not in selected_ids:
                selected_ids.add(ds_id)
                selected.append(ds)

    # Phase 2: Fill remaining slots with best overall candidates
    remaining = max_for_embedding - len(selected)
    if remaining > 0:
        for score, ds in scored:
            ds_id = ds.get("id", "")
            if ds_id not in selected_ids:
                selected_ids.add(ds_id)
                selected.append(ds)
                remaining -= 1
                if remaining <= 0:
                    break

    source_dist = {}
    for ds in selected:
        src = ds.get("source", "unknown")
        source_dist[src] = source_dist.get(src, 0) + 1
    logger.info(
        f"Pre-filter: {len(candidates)} -> {len(selected)} candidates. "
        f"Source distribution: {source_dist}"
    )
    return selected


def _score_quality(downloads: int, likes: int) -> float:
    """Dataset completeness and community quality signal."""
    if downloads == 0 and likes == 0:
        return 0.1
    download_score = np.log1p(downloads) / np.log1p(1_000_000)
    like_score = np.log1p(likes) / np.log1p(10_000)
    score = (0.7 * download_score) + (0.3 * like_score)
    return min(max(score, 0.0), 1.0)


def _score_popularity(downloads: int, likes: int) -> float:
    """
    Separate Popularity Score (P_i).
    Pure community popularity signal — distinct from Q_i (completeness)
    and G_i (graph centrality).
    """
    raw = np.log1p(downloads + likes) / np.log1p(1_000_000)
    return min(max(raw, 0.0), 1.0)


def _score_license(license_id) -> float:
    if not license_id:
        return LICENSE_SCORES["unknown"]
    if isinstance(license_id, list):
        license_id = license_id[0] if license_id else "unknown"
    lid = str(license_id).lower().strip()
    return LICENSE_SCORES.get(lid, 0.2)


def _score_freshness(last_modified: str | None) -> float:
    if not last_modified:
        return 0.3
    try:
        dt = date_parser.parse(last_modified)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff_days = (now - dt).days
        max_days = 3650
        if diff_days < 0:
            return 1.0
        return max(0.0, 1.0 - (diff_days / max_days))
    except Exception:
        return 0.3


# ── Domain keyword enforcement ──────────────────────────────────────────────
DOMAIN_REQUIRED_KEYWORDS: Dict[str, set] = {
    "nlp":    {"text", "review", "corpus", "language", "nlp", "sentiment",
              "comment", "document", "word", "sentence", "prompt", "instruction"},
    "cv":     {"image", "photo", "video", "pixel", "visual", "picture",
              "frame", "segmentation", "detection", "x-ray", "fundus"},
    "audio":  {"audio", "speech", "sound", "voice", "music", "acoustic",
              "waveform", "transcript"},
    "tabular":{"csv", "table", "column", "structured", "spreadsheet",
              "excel", "numeric", "feature"},
}


def _apply_hard_constraints(
    query: str,
    candidates: List[Dict[str, Any]],
    tasks: List[str] | None,
    domain: str | None,
    anti_keywords: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Universal constraint layer:
    1. Dynamic constraint token gating
    2. Anti-keyword signal ratio filtering
    3. Domain/Modality keyword enforcement (Aggressive - Fix 2 & 5)
    """
    query_lower = query.lower()

    # ── 1. Extract High-Information Tokens ──
    GENERIC_TERMS = {
        "dataset", "data", "model", "training", "deep",
        "learning", "machine", "ai", "ml",
        "classification", "segmentation", "detection",
        "regression", "prediction", "analysis",
        "object", "image", "text", "audio",
        "task", "project", "find", "search",
    }

    tokens = re.findall(r"\b[a-zA-Z\-]{3,}\b", query_lower)
    constraint_terms = list(set(
        t for t in tokens if t not in GENERIC_TERMS
    ))

    # ── 2. Determine If Query Is Strict ──
    strict_query = len(constraint_terms) >= 2

    # ── 3. Domain keyword set ──
    domain_kws = DOMAIN_REQUIRED_KEYWORDS.get(domain, set()) if domain else set()
    anti_kw_lower = [ak.lower() for ak in (anti_keywords or [])]

    filtered = []
    dropped = 0

    for ds in candidates:
        name = (ds.get("id") or "").lower()
        desc = (ds.get("description") or "").lower()
        tags = " ".join(ds.get("tags", [])).lower()
        ds_text = f"{name} {desc} {tags}"

        # ── 1. Modality-based Cross-Domain Rejection (Aggressive) ──
        if domain == "cv" and any(w in ds_text for w in ["audio", "speech", "waveform"]):
            if not any(v in ds_text for v in ["vision", "image", "multimodal", "cv"]):
                dropped += 1
                continue
        
        if domain == "tabular" and any(w in ds_text for w in ["image", "vision", "audio"]):
            if "csv" not in ds_text and "excel" not in ds_text:
                dropped += 1
                continue

        # ── 2. Information Token Matching (if strict) ──
        if strict_query:
            matches = sum(1 for term in constraint_terms if term in ds_text)
            if matches < 1:
                dropped += 1
                continue

        # ── 3. Domain keyword enforcement ──
        if domain_kws:
            has_domain_kw = any(kw in ds_text for kw in domain_kws)
            # tabular is tricky, allow fallback if tags suggest structured data
            if not has_domain_kw:
                if domain == "tabular" and any(w in ds_text for w in ["dataset", "data", "csv"]):
                    pass
                else:
                    dropped += 1
                    continue

        # ── 4. Anti-keyword signal ratio check ──
        if anti_kw_lower:
            positive_hits = sum(1 for term in constraint_terms if term in ds_text) if strict_query else 1
            negative_hits = sum(1 for ak in anti_kw_lower if ak in ds_text)
            if negative_hits >= 2 and negative_hits > positive_hits:
                dropped += 1
                continue

        filtered.append(ds)

    if dropped > 0:
        logger.info(f"Constraint gating removed {dropped} weakly/negatively/off-domain candidates.")

    if not filtered:
        logger.warning("Constraint gating removed all candidates. Falling back to top-3 to avoid empty result.")
        return candidates[:3]

    return filtered

def _dataset_size_filter(ds):
    size = ds.get("downloads",0)
    desc = ds.get("description","").lower()

    if size < 50 and "benchmark" not in desc:
        return False
    return True
def rank_datasets(
    query: str,
    dataset_candidates: List[Dict[str, Any]],
    tasks: List[str] | None = None,
    domain: str | None = None,
    keyword_variants: List[str] | None = None,
    anti_keywords: List[str] | None = None,
    preferred_format: str | None = None,
    top_k: int = 7,
    stop_event: threading.Event | None = None
    
) -> List[Dict[str, Any]]:
    # Fix 7: Multi-source Real Dataset Filtering
    candidates = [c for c in dataset_candidates if _is_real_dataset(c)]
    
    # Fix 3: Remove pure research papers (ArXiv papers without 'dataset' in desc)
    candidates = [
        c for c in candidates
        if not (c.get("source") == "arxiv" and "dataset" not in c.get("description","").lower())
    ]
    candidates = [c for c in candidates if _dataset_size_filter(c)]
    """
    Multi-factor ranking engine with split-field embeddings + dataset intelligence.

    Scoring formula:
    Scoring formula:
      R_i = (0.45*E + 0.20*T + 0.10*K + 0.10*Q + 0.10*G + 0.05*P)
            * type_match_penalty * intent_bonus * src_penalty * anti_keyword_penalty

    Where:
      E  = Weighted semantic similarity (0.4*title + 0.3*tags + 0.3*desc)
      T  = Task alignment (also split-field)
      K  = Keyword overlap (sqrt normalized)
      Q  = Quality (completeness)
      P  = Popularity (community signal)
      G  = Graph relevance (built across type-filtered topology)
    """
    if not dataset_candidates:
        return []

    # ── 0. DETERMINISTIC GATING ──
    dataset_candidates = _apply_hard_constraints(
        query, dataset_candidates, tasks, domain, anti_keywords
    )

    # ── STAGE 1.5: Fast Pre-Filter (adaptive sizing) ──
    filtered_candidates = _prefilter_candidates(query, dataset_candidates)

    # ── 1. Semantic Similarity (E_i) — Split-Field Embeddings ──
    query_parts = [query]
    if domain:
        query_parts.append(domain)
    if tasks:
        query_parts.append(", ".join(tasks))

    enriched_query = " | ".join(query_parts)

    if keyword_variants and len(keyword_variants) > 0:
        queries_to_embed = [enriched_query] + keyword_variants[:3]
        query_embs = get_embeddings(queries_to_embed)
        query_emb = np.mean(query_embs, axis=0).reshape(1, -1)
    else:
        query_emb = get_embedding(enriched_query).reshape(1, -1)

    # Build separate field texts
    titles = []
    descriptions = []
    tags_list = []

    for ds in filtered_candidates:
        if stop_event and stop_event.is_set():
            logger.info("Ranking aborted via stop_event.")
            return []
            
        raw_title = ds.get("id", "")
        titles.append(_clean_title_for_embedding(raw_title))

        desc = ds.get("description", "")[:250]
        if not desc.strip():
            desc = raw_title
        descriptions.append(desc)

        tags = " ".join(ds.get("tags", [])[:10])
        if not tags.strip():
            tags = raw_title
        tags_list.append(tags)

    # Check abort before embeddings
    if stop_event and stop_event.is_set():
        logger.info("Ranking aborted before embeddings.")
        return []

    # Batch embed all three fields
    title_embs = get_embeddings(titles)
    
    if stop_event and stop_event.is_set():
        logger.info("Ranking aborted during embeddings.")
        return []
        
    desc_embs = get_embeddings(descriptions)
    
    if stop_event and stop_event.is_set():
        logger.info("Ranking aborted during embeddings.")
        return []
        
    tags_embs = get_embeddings(tags_list)

    # Weighted combination: 0.4 title + 0.3 tags + 0.3 description
    title_sims = cosine_similarity(query_emb, title_embs)[0]
    tags_sims = cosine_similarity(query_emb, tags_embs)[0]
    desc_sims = cosine_similarity(query_emb, desc_embs)[0]

    semantic_sims = (0.4 * title_sims) + (0.3 * tags_sims) + (0.3 * desc_sims)

    # ── 2. Task Alignment (T_i) — same split-field approach ──
    task_scores = []
    if tasks:
        task_query = " ".join(tasks)
        task_query_emb = get_embedding(task_query).reshape(1, -1)

        task_title_sims = cosine_similarity(task_query_emb, title_embs)[0]
        task_tags_sims = cosine_similarity(task_query_emb, tags_embs)[0]
        task_desc_sims = cosine_similarity(task_query_emb, desc_embs)[0]

        task_sims = (0.4 * task_title_sims) + (0.3 * task_tags_sims) + (0.3 * task_desc_sims)
        task_scores = [max(0.0, float(s)) for s in task_sims]
    else:
        task_scores = [0.5 for _ in filtered_candidates]

    # ── 3. Dataset Type Filter + Graph Mapping ──
    if stop_event and stop_event.is_set():
        return []
        
    # Map valid types first
    valid_candidates = []
    type_penalties = []
    for ds in filtered_candidates:
        DT_i = dataset_intelligence.type_match_score(ds, domain)
        type_penalties.append(DT_i)
        
    candidate_ids = [ds["id"] for ds in filtered_candidates]
    # Graph layer maps topology across explicitly retrieved IDs + type penalties
    graph_scores = graph_service.calculate_graph_scores(candidate_ids)
    
    # Apply type isolation to graph structure dynamically (penalty logic happens in final composite)

    # ── Keyword Overlap (K_i) ──
    query_words = set(re.findall(r'\w+', query.lower()))
    keyword_overlaps = [_keyword_overlap_score(query_words, ds) for ds in filtered_candidates]

    # ── Extract constraint terms for anti-keyword ratio ──
    _GENERIC = {
        "dataset", "data", "model", "training", "deep",
        "learning", "machine", "ai", "ml",
        "classification", "segmentation", "detection",
        "regression", "prediction", "analysis",
        "object", "image", "text", "audio",
        "task", "project", "find", "search",
    }
    tokens = re.findall(r"\b[a-zA-Z\-]{3,}\b", query.lower())
    constraint_terms = list(set(t for t in tokens if t not in _GENERIC))

    # ── Combine all dimensions ──
    final_candidates = []
    raw_scores = []
    for i, ds in enumerate(filtered_candidates):
        if stop_event and stop_event.is_set():
            return []
            
        E_i = float(semantic_sims[i])
        T_i = float(task_scores[i])
        K_i = float(keyword_overlaps[i])

        if tasks and T_i < 0.10:
            continue

        Q_i = _score_quality(ds.get("downloads", 0), ds.get("likes", 0))
        P_i = _score_popularity(ds.get("downloads", 0), ds.get("likes", 0))
        G_i = graph_scores.get(ds["id"], 0.0)
        L_i = _score_license(ds.get("license", "unknown"))
        F_i = _score_freshness(ds.get("last_modified"))

        # ── Intelligence signals ──
        DT_i = type_penalties[i]
        FM_i = dataset_intelligence.format_match_score(ds, preferred_format)
        B_i = _benchmark_score(ds)
        A_i = _annotation_score(ds)

        # F_i = _score_freshness(ds.get("last_modified"))
        source = ds.get("source", "unknown").lower()
        trust_score = SOURCE_TRUST_SCORES.get(source, 0.4)

        # ── Final Adaptive Re-ranking (LambdaRank Integration) ──
        features = {
            "semantic": E_i,
            "task": T_i,
            "quality": Q_i,
            "license": L_i,
            "freshness": F_i,
            "graph": G_i
        }
        
        # Use LightGBM model if trained, otherwise adaptive heuristic
        base_score = learning_ranker.predict_score(features)

        # ── Additive task intent bonus (capped at 0.10) ──
        intent_bonus = _task_intent_bonus(query, tasks or [], ds)

        # ── Source penalty (untrusted sources penalized) ──
        src_penalty = _source_penalty(ds)

        # ── Anti-keyword signal ratio penalty ──
        anti_penalty = _anti_keyword_penalty(ds, anti_keywords or [], constraint_terms)
        
        # ── Graph + Type Isolation Penalty ──
        if DT_i < 0.5:
            base_score *= 0.7  # deducing for type mismatch

        final_score = (base_score + intent_bonus + (B_i * 0.1) + (A_i * 0.1)) * src_penalty * anti_penalty

        breakdown = {
            "semantic": E_i,
            "keyword_overlap": K_i,
            "task": T_i,
            "quality": Q_i,
            "popularity": P_i,
            "graph": G_i,
            "trust": trust_score,
            "freshness": F_i,
            "benchmark_bonus": B_i,
            "annotation_bonus": A_i
        }
        ds["ranking_breakdown"] = breakdown
        ds["raw_similarity_score"] = final_score

        raw_scores.append(final_score)
        final_candidates.append(ds)

    # Normalize scores
    if raw_scores:
        min_score = min(raw_scores)
        max_score = max(raw_scores)
        for ds in final_candidates:
            score = ds["raw_similarity_score"]
            if max_score > min_score:
                normalized_score = (score - min_score) / (max_score - min_score)
            else:
                normalized_score = 0.5
            ds["similarity_score"] = float(normalized_score * 0.85)

    ranked = sorted(final_candidates, key=lambda x: x["similarity_score"], reverse=True)
    
    # Apply categorization (Fix 7/10: Split Results)
    all_practical = []
    all_research = []
    academic_sources = ["ieee", "arxiv", "semantic_scholar", "semanticscholar"]
    
    for ds in ranked:
        src = ds.get("source", "").lower()
        if src in academic_sources or ds.get("is_paper_seed"):
            ds["dataset_category"] = "research_benchmark"
            all_research.append(ds)
        else:
            ds["dataset_category"] = "practical"
            all_practical.append(ds)
            
    return {
        "all": ranked[:top_k],
        "practical": all_practical[:top_k],
        "research_benchmarks": all_research[:top_k]
    }