"""Governed hybrid retriever for the report and advisor pipelines.

Upgrades over the original keyword-only retriever:

* zh-bigram / en-word tokenization (shared with the hashing embedding) instead
  of single-character CJK tokens, which caused systematic false matches.
* Hybrid scoring: keyword cosine fused with the offline hashing-vector cosine
  built at ingest time; degrades gracefully to keyword-only when numpy or the
  vector files are unavailable.
* Governance hygiene: per-source usage-boilerplate chunks (section_role =
  ``governance``) never compete in report retrieval; chunks that carry a
  sensitive allowed_use without a high-trust evidence class are excluded from
  sensitive requests entirely.
* Diversification: per-source result caps so one guideline cannot fill the
  whole evidence list, plus the existing required-use coverage fill.
* Optional fulltext expansion: locally ingested PDF chunks (vector_store) can
  be merged into the evidence pool under the same governance filters, giving
  the generator quotable passage-level material with page locators.
"""

from __future__ import annotations

import json
import threading
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.schemas.report import Evidence
from app.services.chunking import build_embedding_text, tokenize_for_match
from app.services.config_loader import development_override, resolve_project_path, load_yaml_config
from app.services.fingerprints import catalog_fingerprint
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES, included_sources


BP_VALUE_RE = re.compile(r"\b\d{2,3}\s*[/／]\s*\d{2,3}\b")
SENSITIVE_USES = {"emergency_alert", "medication_safety", "special_population"}

FULLTEXT_CHUNKS_PATH = "knowledge_base/vector_store/fulltext_chunks.jsonl"

# Per store: (OpenAI embedding index, offline hashing index). The OpenAI index
# is preferred when an API key is configured and the index covers the current
# chunk ids; otherwise the hashing index serves, and with neither the scorer
# stays keyword-only. All three tiers share the same npz layout.
VECTOR_STORE_PATHS = {
    "processed": (
        "knowledge_base/vector_store/openai_embeddings_processed_chunks.npz",
        "knowledge_base/vector_store/processed_hashing_vectors.npz",
    ),
    "fulltext": (
        "knowledge_base/vector_store/openai_embeddings_fulltext_chunks.npz",
        "knowledge_base/vector_store/fulltext_hashing_vectors.npz",
    ),
}


@dataclass
class RetrievalResult:
    evidence: List[Evidence] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


_BACKEND_STATE = threading.local()


def last_retrieval_backend() -> str:
    return str(getattr(_BACKEND_STATE, "value", "keyword"))


@lru_cache(maxsize=4)
def _catalog_governance_cached(_fingerprint: str) -> Dict[str, Dict]:
    return {str(item.get("source_id")): item for item in included_sources() if item.get("source_id")}


def _current_catalog_governance() -> Dict[str, Dict]:
    return _catalog_governance_cached(catalog_fingerprint())


def _apply_current_catalog_governance(chunks: Iterable[Dict]) -> List[Dict]:
    live = _current_catalog_governance()
    governed: List[Dict] = []
    for original in chunks:
        source = live.get(str(original.get("source_id") or ""))
        if source is None:
            continue
        chunk = dict(original)
        chunk["allowed_uses"] = sorted(
            set(_as_list(original.get("allowed_uses"))) & set(_as_list(source.get("allowed_uses")))
        )
        chunk["evidence_class"] = source.get("evidence_class", chunk.get("evidence_class"))
        chunk["source_quality_score"] = source.get(
            "source_quality_score", chunk.get("source_quality_score")
        )
        chunk["review_status"] = "included"
        if chunk["allowed_uses"]:
            governed.append(chunk)
    return governed


def _tokenize(text: str) -> List[str]:
    return tokenize_for_match(text)


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _file_signature(path_string: str) -> Tuple[str, float]:
    path = resolve_project_path(path_string)
    try:
        return (str(path), path.stat().st_mtime)
    except OSError:
        return (str(path), 0.0)


@lru_cache(maxsize=8)
def _load_chunks_cached(path_string: str, mtime: float) -> tuple:
    path = resolve_project_path(path_string)
    if not path.exists():
        return tuple()
    chunks = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return tuple(chunks)


def _load_chunks(chunks_path: str = None) -> List[Dict]:
    settings = load_yaml_config("config/settings.yaml").get("retrieval", {})
    path_string = chunks_path or settings.get("chunks_path", "knowledge_base/processed/chunks.jsonl")
    return list(_load_chunks_cached(*_file_signature(path_string)))


# ---------------------------------------------------------------------------
# Optional hashing-vector index (offline, numpy only)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _load_vector_index(path_string: str, mtime: float):
    """Return (ids->row dict, embeddings ndarray) or None when unavailable."""
    if mtime <= 0:
        return None
    try:
        import numpy as np
    except Exception:
        return None
    path = resolve_project_path(path_string)
    try:
        data = np.load(path, allow_pickle=True)
        ids = [str(item) for item in data["ids"]]
        embeddings = data["embeddings"].astype("float32")
    except Exception:
        return None
    if embeddings.shape[0] != len(ids) or embeddings.shape[0] == 0:
        return None
    return ({chunk_id: row for row, chunk_id in enumerate(ids)}, embeddings)


def _hashing_query_vector(query_text: str, dims: int):
    try:
        from app.services.fulltext_vector_index import hashing_embedding
    except Exception:
        return None
    return hashing_embedding(query_text, dims=dims)


# Successful query embeddings are memoized (advisor turns and evaluation runs
# repeat intents); API failures trip a short backoff so reports never queue up
# behind a dead endpoint.
_OPENAI_QUERY_CACHE: Dict[Tuple[str, int, str], object] = {}
_OPENAI_QUERY_CACHE_MAX = 512
_OPENAI_BACKOFF_UNTIL = 0.0
_OPENAI_BACKOFF_SEC = 300.0


def _query_cache_enabled() -> bool:
    """The query-embedding cache is on by default; the E1 ablation harness sets
    ``RETRIEVAL_DISABLE_QUERY_CACHE=1`` so retrieval variants cannot share
    cached vectors and contaminate each other's timing/results."""
    return development_override("RETRIEVAL_DISABLE_QUERY_CACHE").strip().lower() not in {"1", "true", "on", "yes"}


def _openai_query_timeout(settings: Dict) -> float:
    """OpenAI query-embedding timeout, with env override for batch/eval runs.

    ``OPENAI_QUERY_TIMEOUT_SEC`` lets the experiment harness lift the default
    8s so embedding calls under load don't time out and trip the shared backoff
    (which would silently degrade the OpenAI backend to keyword-only)."""
    override = development_override("OPENAI_QUERY_TIMEOUT_SEC").strip()
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    return float(settings.get("openai_query_timeout_sec", 8))


def _openai_query_vector(query_text: str, dims: int):
    """Embed the query via the configured OpenAI endpoint; None disables.

    None is returned when no API key is configured, the configured dimensions
    do not match the index, or the endpoint recently failed (backoff window) —
    each case degrades to the hashing backend / keyword-only scoring.
    """
    global _OPENAI_BACKOFF_UNTIL
    import time

    try:
        from app.services.config_loader import load_openai_embedding_config
    except Exception:
        return None
    config = load_openai_embedding_config()
    if not config.api_key:
        return None
    cache_enabled = _query_cache_enabled()
    cache_key = (config.model, dims, query_text)
    if cache_enabled:
        cached = _OPENAI_QUERY_CACHE.get(cache_key)
        if cached is not None:
            return cached
    if time.monotonic() < _OPENAI_BACKOFF_UNTIL:
        return None
    settings = load_yaml_config("config/settings.yaml").get("retrieval", {})
    timeout = _openai_query_timeout(settings)
    try:
        from app.services.openai_embedding_index import embed_texts

        vectors, _, _ = embed_texts([query_text], config=config, timeout_sec=timeout, max_retries=0)
    except Exception:
        _OPENAI_BACKOFF_UNTIL = time.monotonic() + _OPENAI_BACKOFF_SEC
        return None
    if vectors.shape[0] != 1 or vectors.shape[1] != dims:
        return None
    vector = vectors[0]
    if cache_enabled:
        if len(_OPENAI_QUERY_CACHE) >= _OPENAI_QUERY_CACHE_MAX:
            _OPENAI_QUERY_CACHE.clear()
        _OPENAI_QUERY_CACHE[cache_key] = vector
    return vector


def _prefetch_openai_query_vectors(texts: Sequence[str]) -> None:
    """Embed all unseen query texts in ONE batched API call.

    Without this, every retrieval intent costs a serial embeddings roundtrip
    (a single report carries several intents, easily blowing the latency
    budget on slow networks). Failures trip the shared backoff exactly like
    the per-query path.
    """
    global _OPENAI_BACKOFF_UNTIL
    import time

    # Prefetch only makes sense as a cache warm-up; with the cache disabled the
    # per-query path embeds on demand and prefetch would just pollute the cache.
    if not _query_cache_enabled():
        return
    settings = load_yaml_config("config/settings.yaml").get("retrieval", {})
    backend = _resolve_embedding_backend()
    if backend not in {"auto", "openai"}:
        return
    try:
        from app.services.config_loader import load_openai_embedding_config
    except Exception:
        return
    config = load_openai_embedding_config()
    if not config.api_key or time.monotonic() < _OPENAI_BACKOFF_UNTIL:
        return
    # Collect the dimensions of every loadable OpenAI index (normally one).
    dims_set = set()
    for store in VECTOR_STORE_PATHS:
        index = _load_vector_index(*_file_signature(VECTOR_STORE_PATHS[store][0]))
        if index is not None:
            dims_set.add(int(index[1].shape[1]))
    if not dims_set:
        return
    unique_texts = list(dict.fromkeys(text for text in texts if text and text.strip()))
    timeout = _openai_query_timeout(settings)
    for dims in dims_set:
        missing = [
            text for text in unique_texts
            if (config.model, dims, text) not in _OPENAI_QUERY_CACHE
        ]
        if not missing:
            continue
        try:
            from app.services.openai_embedding_index import embed_texts

            vectors, _, _ = embed_texts(missing, config=config, timeout_sec=max(timeout, 15), max_retries=0)
        except Exception:
            _OPENAI_BACKOFF_UNTIL = time.monotonic() + _OPENAI_BACKOFF_SEC
            return
        if vectors.shape[0] != len(missing) or vectors.shape[1] != dims:
            continue
        if len(_OPENAI_QUERY_CACHE) + len(missing) >= _OPENAI_QUERY_CACHE_MAX:
            _OPENAI_QUERY_CACHE.clear()
        for text, vector in zip(missing, vectors):
            _OPENAI_QUERY_CACHE[(config.model, dims, text)] = vector


def _vector_scores(
    query_text: str,
    chunk_ids: Sequence[str],
    vectors_path: str,
    embed_query=_hashing_query_vector,
) -> Optional[Dict[str, float]]:
    """Cosine similarity of the query against one vector index, by chunk id.

    One vectorized matvec over the whole store, then a lookup for the candidate
    ids. Returns None when the vector index is unavailable, does not cover the
    current chunk ids (e.g. stale index after re-ingest), or the query cannot
    be embedded — so callers fall back to the next tier.
    """
    index = _load_vector_index(*_file_signature(vectors_path))
    if index is None:
        return None
    id_to_row, embeddings = index
    known = [chunk_id for chunk_id in chunk_ids if chunk_id in id_to_row]
    if not known or len(known) < max(2, int(len(chunk_ids) * 0.5)):
        return None
    try:
        import numpy as np
    except Exception:
        return None
    query_vector = embed_query(query_text, int(embeddings.shape[1]))
    if query_vector is None:
        return None
    query_vector = query_vector.astype(embeddings.dtype)
    with np.errstate(all="ignore"):
        all_scores = embeddings @ query_vector
    # Zero-norm rows (empty chunks) can yield NaN on some BLAS backends; they
    # must rank at 0, never poison the sort.
    all_scores = np.nan_to_num(all_scores, nan=0.0, posinf=0.0, neginf=0.0)
    scores: Dict[str, float] = {}
    for chunk_id in known:
        scores[chunk_id] = float(max(0.0, all_scores[id_to_row[chunk_id]]))
    return scores


def _resolve_embedding_backend() -> str:
    """Vector backend, with an env override for deterministic runs.

    ``RETRIEVAL_EMBEDDING_BACKEND`` (tests, quality gate) takes precedence over
    ``retrieval.embedding_backend`` in settings.yaml — so CI and the calibrated
    gate stay offline even when an embedding API key is configured locally.
    """
    override = development_override("RETRIEVAL_EMBEDDING_BACKEND").strip().lower()
    if override in {"auto", "openai", "hashing", "off"}:
        return override
    settings = load_yaml_config("config/settings.yaml").get("retrieval", {})
    return str(settings.get("embedding_backend", "auto")).lower()


def _store_chunks_mtime(store: str) -> float:
    if store == "fulltext":
        return _file_signature(FULLTEXT_CHUNKS_PATH)[1]
    settings = load_yaml_config("config/settings.yaml").get("retrieval", {})
    return _file_signature(settings.get("chunks_path", "knowledge_base/processed/chunks.jsonl"))[1]


def _vector_index_is_fresh(vectors_path: str, chunks_mtime: float) -> bool:
    """A vector index older than its chunks file was built from different text.

    Chunk ids keep the same naming scheme across re-ingests, so id-coverage
    alone cannot detect that the underlying content changed; the mtime ordering
    can. Stale indexes are skipped until rebuilt.
    """
    vectors_mtime = _file_signature(vectors_path)[1]
    if vectors_mtime <= 0:
        return False
    return vectors_mtime >= chunks_mtime


def _store_vector_scores(
    query_text: str, chunk_ids: Sequence[str], store: Optional[str]
) -> Optional[Dict[str, float]]:
    """Resolve the embedding backend for a store and score the query.

    ``retrieval.embedding_backend``: ``auto`` (default) prefers the OpenAI
    index and falls back to the offline hashing index; ``openai`` / ``hashing``
    pin one backend; ``off`` disables vectors (keyword-only).
    """
    if store not in VECTOR_STORE_PATHS:
        return None
    backend = _resolve_embedding_backend()
    openai_path, hashing_path = VECTOR_STORE_PATHS[store]
    chunks_mtime = _store_chunks_mtime(store)
    if backend in {"auto", "openai"} and _vector_index_is_fresh(openai_path, chunks_mtime):
        scores = _vector_scores(query_text, chunk_ids, openai_path, _openai_query_vector)
        if scores is not None:
            _BACKEND_STATE.value = "openai_embedding"
            return scores
    if backend == "openai":
        return None
    if backend in {"auto", "hashing"} and _vector_index_is_fresh(hashing_path, chunks_mtime):
        scores = _vector_scores(query_text, chunk_ids, hashing_path, _hashing_query_vector)
        if scores is not None:
            _BACKEND_STATE.value = "local_hashing"
        return scores
    return None


_TOKEN_CACHE_KEY = "_match_token_set"


def _chunk_token_set(chunk: Dict) -> frozenset:
    """Tokenize a chunk once and memoize on the (cached, shared) dict itself."""
    cached = chunk.get(_TOKEN_CACHE_KEY)
    if cached is not None:
        return cached
    content = build_embedding_text(chunk, str(chunk.get("content", "")))
    token_set = frozenset(_tokenize(content))
    chunk[_TOKEN_CACHE_KEY] = token_set
    return token_set


def _keyword_score(query_tokens: Sequence[str], chunk: Dict) -> float:
    if not query_tokens:
        return 0.0
    chunk_set = _chunk_token_set(chunk)
    if not chunk_set:
        return 0.0
    query_set = set(query_tokens)
    overlap = len(query_set & chunk_set)
    if overlap == 0:
        return 0.0
    return overlap / math.sqrt(len(query_set) * len(chunk_set))


def _quality_boost(chunk: Dict) -> float:
    try:
        return min(float(chunk.get("source_quality_score") or 0), 25) / 250
    except (TypeError, ValueError):
        return 0.0


def _rerank_score(base_score: float, chunk: Dict, required_uses: Set[str], intent: str) -> float:
    allowed_uses = set(_as_list(chunk.get("allowed_uses")))
    score = base_score
    if required_uses:
        overlap = len(required_uses & allowed_uses)
        score += 0.08 * overlap
        if required_uses <= allowed_uses:
            score += 0.04
    if chunk.get("evidence_class") in HIGH_TRUST_EVIDENCE_CLASSES:
        score += 0.05
    if chunk.get("region") in {"CN", "AHA", "US", "global"}:
        score += 0.02
    if chunk.get("topic") and str(chunk.get("topic")).replace("_", " ") in intent.lower():
        score += 0.03
    return score


def infer_allowed_uses(retrieval_intents: Iterable[str]) -> Set[str]:
    text = " ".join(retrieval_intents).lower()
    has_bp_value = bool(BP_VALUE_RE.search(text))
    ppg_context = any(term in text for term in ["ppg", "cuffless", "无袖带", "摄像头", "手机", "手指", "光学", "估算"])
    ptt_context = any(term in text for term in ["pat", "ptt", "pulse arrival", "pulse transit", "脉搏到达", "脉搏传导", "传导时间", "到达时间"])
    medication_context = any(term in text for term in ["medication", "drug", "medicine", "pharmacological", "服药", "服用", "停药", "用药", "降压药", "药物", "药物治疗", "调药", "加药", "剂量", "自行"])
    special_context = any(term in text for term in ["pregnancy", "pregnant", "妊娠", "孕", "diabetes", "kidney", "ckd", "cvd", "cardiovascular", "糖尿", "肾", "老年", "65", "心血管", "既往心血管病", "特殊人群"])
    cuffless_question = ppg_context and any(
        term in text
        for term in [
            "准确",
            "可靠",
            "替代",
            "代替",
            "只能看趋势",
            "趋势参考",
            "不能诊断",
            "不能替代",
            "局限",
            "validation",
            "limitation",
            "reliable",
            "accurate",
        ]
    )
    ppg_motion_or_sensor_question = ppg_context and any(
        term in text
        for term in [
            "可穿戴",
            "光学传感器",
            "活动状态",
            "运动",
            "误差",
            "motion",
            "artifact",
            "sensor",
            "wearable",
            "伪影",
        ]
    )
    explicit_bp_category_terms = any(
        term in text
        for term in [
            "血压分类",
            "参考范围",
            "正常参考",
            "stage",
            "elevated",
            "normal",
            "category",
            "读数",
            "reading",
            "中国 高血压 指南",
            "aha 血压分类",
            "blood pressure category",
        ]
    )
    bp_category_question = has_bp_value or explicit_bp_category_terms or ("偏高" in text and not special_context and not medication_context)
    uses: Set[str] = set()
    if any(term in text for term in ["emergency", "urgent", "180", "120", "胸痛", "气短", "急救", "严重", "肢体", "视物", "说话"]):
        uses.add("emergency_alert")
    if medication_context:
        uses.add("medication_safety")
    if any(term in text for term in ["pregnancy", "pregnant", "妊娠", "孕"]):
        uses.add("special_population")
    if special_context:
        uses.add("special_population")
    if any(term in text for term in ["lifestyle", "sodium", "exercise", "weight", "sleep", "smoking", "减盐", "运动", "体重", "睡眠", "戒烟"]) and not ppg_motion_or_sensor_question:
        uses.add("lifestyle")
    if bp_category_question:
        uses.add("bp_category_reference")
    if cuffless_question or any(term in text for term in ["无袖带", "cuffless", "信号", "置信度", "quality_score", "confidence", "motion", "artifact", "motion_artifact_score", "伪影", "环境光", "ambient_light", "肤色", "接触压力", "contact_pressure", "采集时长", "传感器位置", "finger_coverage"]):
        uses.add("cuffless_ppg_limitations")
    if any(term in text for term in ["信号", "置信度", "quality_score", "confidence", "motion", "artifact", "motion_artifact_score", "伪影", "环境光", "ambient_light", "光照", "过曝", "过暗", "肤色", "接触压力", "contact_pressure", "按压力度", "采集时长", "传感器位置", "finger_coverage", "手指覆盖", "手指移动", "覆盖不完整"]):
        uses.update({"signal_quality", "remeasurement"})
    if ppg_motion_or_sensor_question:
        uses.update({"signal_quality", "research_background"})
    if ptt_context:
        uses.update({"cuffless_ppg_limitations", "research_background"})
    device_context = any(term in text for term in ["home", "monitoring", "upper arm", "validated", "上臂", "家庭", "stride", "validatebp", "验证设备"])
    recheck_context = any(term in text for term in ["复测", "复核", "记录", "连续", "趋势", "rest", "reading"])
    if device_context:
        uses.update({"home_bp_monitoring", "device_advice"})
    if recheck_context and not (uses == {"special_population"}):
        uses.add("remeasurement")
    if "血压计" in text and not cuffless_question:
        uses.update({"home_bp_monitoring", "device_advice"})
    if cuffless_question and not bp_category_question:
        uses.discard("home_bp_monitoring")
        uses.discard("remeasurement")
    return uses


def _chunk_allowed(
    chunk: Dict,
    required_uses: Set[str],
    evidence_classes: Optional[Set[str]],
    min_quality_score: Optional[float],
    include_governance: bool = False,
) -> bool:
    if chunk.get("review_status") == "excluded":
        return False
    if not include_governance and chunk.get("section_role") == "governance":
        return False
    if evidence_classes and chunk.get("evidence_class") not in evidence_classes:
        return False
    if min_quality_score is not None:
        try:
            if float(chunk.get("source_quality_score") or 0) < min_quality_score:
                return False
        except (TypeError, ValueError):
            return False

    allowed_uses = set(_as_list(chunk.get("allowed_uses")))
    request_is_sensitive = bool(required_uses & SENSITIVE_USES)
    if (
        request_is_sensitive
        and (allowed_uses & SENSITIVE_USES)
        and chunk.get("evidence_class") not in HIGH_TRUST_EVIDENCE_CLASSES
    ):
        # In a sensitive request every source that even carries a sensitive use
        # must be high trust; otherwise it can surface beside emergency or
        # medication guidance with insufficient evidentiary backing.
        return False
    if not required_uses:
        return True

    matched_uses = allowed_uses & required_uses
    if not matched_uses:
        return False
    if (matched_uses & SENSITIVE_USES) and chunk.get("evidence_class") not in HIGH_TRUST_EVIDENCE_CLASSES:
        return False
    return True


def _chunk_to_evidence(chunk: Dict, used_for: str, score: float) -> Evidence:
    content = re.sub(r"\s+", " ", chunk.get("content", "")).strip()
    snippet = content[:240] + ("..." if len(content) > 240 else "")
    return Evidence(
        source_id=chunk.get("chunk_id") or chunk.get("source_id") or "unknown_source",
        title=chunk.get("title") or "Untitled source",
        url=chunk.get("url"),
        used_for=used_for,
        organization=chunk.get("organization"),
        region=chunk.get("region"),
        topic=chunk.get("topic"),
        language=chunk.get("language"),
        evidence_class=chunk.get("evidence_class"),
        source_quality_score=float(chunk.get("source_quality_score")) if str(chunk.get("source_quality_score", "")).replace(".", "", 1).isdigit() else None,
        allowed_uses=_as_list(chunk.get("allowed_uses")),
        review_status=chunk.get("review_status"),
        score=round(score, 4),
        snippet=snippet,
        year=str(chunk.get("year")) if chunk.get("year") not in (None, "") else None,
        doi=str(chunk.get("doi")) if chunk.get("doi") not in (None, "") else None,
        pmid=str(chunk.get("pmid")) if chunk.get("pmid") not in (None, "") else None,
    )


def _parent_source_id(chunk: Dict) -> str:
    return str(chunk.get("source_id") or chunk.get("chunk_id") or chunk.get("title") or "unknown")


def _diversify(ranked: List[tuple], limit: int, per_source_cap: int = 2) -> List[tuple]:
    """Greedy top-score selection with a per-source cap.

    Stops one guideline's many chunks from monopolising the evidence list, so
    the reference list spans more independent sources. ``per_source_cap <= 0``
    disables the cap (E1 ablation: pure top-k by score), letting one source
    fill the whole list.
    """
    if per_source_cap is not None and per_source_cap <= 0:
        return list(ranked[:limit])
    selected: List[tuple] = []
    per_source: Dict[str, int] = {}
    for item in ranked:
        source = _parent_source_id(item[0])
        if per_source.get(source, 0) >= per_source_cap:
            continue
        selected.append(item)
        per_source[source] = per_source.get(source, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def _select_with_use_coverage(
    ranked: List[tuple], required_uses: Set[str], limit: int, per_source_cap: int = 2
) -> List[tuple]:
    selected = _diversify(ranked, limit, per_source_cap=per_source_cap)
    if not required_uses or not selected:
        return selected

    def covered(items: List[tuple]) -> Set[str]:
        uses: Set[str] = set()
        for chunk, _, _ in items:
            uses.update(set(_as_list(chunk.get("allowed_uses"))) & required_uses)
        return uses

    selected_ids = {item[0].get("chunk_id") for item in selected}
    missing = list(required_uses - covered(selected))
    for use in missing:
        candidate = next(
            (
                item for item in ranked
                if item[0].get("chunk_id") not in selected_ids
                and use in set(_as_list(item[0].get("allowed_uses")))
            ),
            None,
        )
        if candidate is None:
            continue
        selected.append(candidate)
        selected_ids = {item[0].get("chunk_id") for item in selected}
    return sorted(selected, key=lambda item: item[1], reverse=True)


def _score_pool(
    intents: List[str],
    candidate_chunks: List[Dict],
    required_uses: Set[str],
    store: Optional[str],
    keyword_weight: float,
    vector_weight: float,
) -> Dict[str, tuple]:
    """Hybrid-score a candidate pool against every intent; keep the best intent."""
    chunk_ids = [str(chunk.get("chunk_id")) for chunk in candidate_chunks]
    scored: Dict[str, tuple] = {}
    for intent in intents:
        query_tokens = _tokenize(intent)
        vector_scores = _store_vector_scores(intent, chunk_ids, store)
        for chunk in candidate_chunks:
            keyword = _keyword_score(query_tokens, chunk)
            vector = (vector_scores or {}).get(str(chunk.get("chunk_id")), 0.0)
            if vector_scores is None:
                base = keyword
            else:
                base = keyword_weight * keyword + vector_weight * vector
            if base <= 0:
                continue
            base += _quality_boost(chunk)
            score = _rerank_score(base, chunk, required_uses, intent)
            chunk_id = chunk.get("chunk_id") or f"{chunk.get('title', 'chunk')}-{len(scored)}"
            previous = scored.get(chunk_id)
            if previous is None or score > previous[1]:
                scored[chunk_id] = (chunk, score, intent)
    return scored


@lru_cache(maxsize=2)
def _load_fulltext_chunks_cached(path_string: str, mtime: float) -> tuple:
    return _load_chunks_cached(path_string, mtime)


def _fulltext_pool(
    intents: List[str],
    required_uses: Set[str],
    evidence_class_filter: Optional[Set[str]],
    min_quality_score: Optional[float],
    keyword_weight: float,
    vector_weight: float,
    top_n: int,
    min_score: float = 0.12,
) -> List[tuple]:
    """Best locally-ingested fulltext passages under the same governance rules."""
    chunks = _apply_current_catalog_governance(
        _load_fulltext_chunks_cached(*_file_signature(FULLTEXT_CHUNKS_PATH))
    )
    if not chunks:
        return []
    candidates = [
        chunk for chunk in chunks
        if _chunk_allowed(chunk, required_uses, evidence_class_filter, min_quality_score)
    ]
    if not candidates:
        return []
    # Vector prefilter: one matvec ranks the whole store; only the best few
    # hundred passages get keyword-scored. Without it, tokenizing ~15k PDF
    # chunks per query blows the report latency budget.
    prefilter_scores = _store_vector_scores(
        " ".join(intents), [str(chunk.get("chunk_id")) for chunk in candidates], "fulltext"
    )
    if prefilter_scores:
        candidates.sort(
            key=lambda chunk: prefilter_scores.get(str(chunk.get("chunk_id")), 0.0), reverse=True
        )
        candidates = candidates[: max(200, top_n * 50)]
    else:
        # No usable vector index: stay cheap rather than slow — cap the pool.
        candidates = candidates[:500]
    scored = _score_pool(
        intents,
        candidates,
        required_uses,
        "fulltext",
        keyword_weight,
        vector_weight,
    )
    ranked = sorted(scored.values(), key=lambda item: item[1], reverse=True)
    ranked = [item for item in ranked if item[1] >= min_score]
    return _diversify(ranked, top_n, per_source_cap=1)


def _resolve_include_fulltext(include_fulltext: Optional[bool], settings: Dict) -> bool:
    if include_fulltext is not None:
        return include_fulltext
    configured = str(settings.get("include_fulltext", "off")).lower()
    if configured in {"true", "on", "always"}:
        return True
    if configured == "auto":
        return resolve_project_path(FULLTEXT_CHUNKS_PATH).exists()
    return False


def _resolve_fusion_weights(settings: Dict) -> Tuple[float, float]:
    """Keyword/vector fusion weights, with env overrides for the E1 weight sweep.

    ``RETRIEVAL_KEYWORD_WEIGHT`` (and optional ``RETRIEVAL_VECTOR_WEIGHT``) let
    the ablation harness scan keyword_weight ∈ {0..1} per variant; 0 = pure
    vector, 1 = pure keyword. Without the env vars, settings.yaml drives.
    """
    keyword_weight = float(settings.get("keyword_weight", 0.6))
    vector_weight = float(settings.get("vector_weight", 0.4))
    kw_override = development_override("RETRIEVAL_KEYWORD_WEIGHT").strip()
    if kw_override:
        try:
            keyword_weight = float(kw_override)
        except ValueError:
            pass
        else:
            vw_override = development_override("RETRIEVAL_VECTOR_WEIGHT").strip()
            vector_weight = float(vw_override) if _is_float(vw_override) else max(0.0, 1.0 - keyword_weight)
    return keyword_weight, vector_weight


def _is_float(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _resolve_per_source_cap(per_source_cap: Optional[int], settings: Dict) -> int:
    """Per-source diversification cap, with an env override for E1 ablation.

    ``RETRIEVAL_PER_SOURCE_CAP`` (set by the dedup-ablation harness) takes
    precedence over the call argument and settings; ``0`` disables dedup so one
    source can fill the whole evidence list.
    """
    override = development_override("RETRIEVAL_PER_SOURCE_CAP").strip()
    if override.lstrip("-").isdigit():
        return int(override)
    if per_source_cap is not None:
        return per_source_cap
    return int(settings.get("per_source_cap", 2))


def retrieve_knowledge(
    retrieval_intents: Iterable[str],
    top_k: int = None,
    chunks_path: str = None,
    allowed_uses: Iterable[str] = None,
    evidence_classes: Iterable[str] = None,
    min_quality_score: float = None,
    include_fulltext: Optional[bool] = None,
    include_governance: bool = False,
    per_source_cap: Optional[int] = None,
) -> RetrievalResult:
    _BACKEND_STATE.value = "keyword"
    settings = load_yaml_config("config/settings.yaml").get("retrieval", {})
    limit = top_k or int(settings.get("top_k", 5))
    keyword_weight, vector_weight = _resolve_fusion_weights(settings)
    fulltext_top_k = int(settings.get("fulltext_top_k", 2))
    source_cap = _resolve_per_source_cap(per_source_cap, settings)
    chunks = _load_chunks(chunks_path)
    if chunks_path is None:
        chunks = _apply_current_catalog_governance(chunks)
    if not chunks:
        return RetrievalResult(
            warnings=["知识库为空或尚未 ingest，已启用模板报告和规则兜底。"]
        )

    intents = list(retrieval_intents)
    # One batched embeddings call for every query this request will make
    # (per-intent scoring plus the joined fulltext prefilter query).
    if chunks_path is None:
        _prefetch_openai_query_vectors(intents + [" ".join(intents)])
    required_uses = set(allowed_uses or []) or infer_allowed_uses(intents)
    evidence_class_filter = set(evidence_classes) if evidence_classes else None
    candidate_chunks = [
        chunk for chunk in chunks
        if _chunk_allowed(chunk, required_uses, evidence_class_filter, min_quality_score, include_governance)
    ]
    if not candidate_chunks:
        candidate_chunks = [
            chunk for chunk in chunks
            if _chunk_allowed(chunk, set(), evidence_class_filter, min_quality_score, include_governance)
        ]

    # Custom chunk files (tests, ad-hoc stores) have no companion vector index.
    store = "processed" if chunks_path is None else None
    scored = _score_pool(
        intents,
        candidate_chunks,
        required_uses,
        store,
        keyword_weight,
        vector_weight,
    )

    if not scored:
        fallback = candidate_chunks[:limit]
        return RetrievalResult(
            evidence=[
                _chunk_to_evidence(chunk, "general health explanation fallback", 0.0)
                for chunk in fallback
            ],
            warnings=["未找到高匹配证据，返回知识库前几个通用知识块。"],
        )

    ranked = sorted(scored.values(), key=lambda item: item[1], reverse=True)
    selected = _select_with_use_coverage(ranked, required_uses, limit, per_source_cap=source_cap)

    # Fulltext passages are for explanatory depth (lifestyle, devices, signal
    # quality). Sensitive requests (emergency / medication / special
    # population) stay on curated high-trust summaries only.
    request_is_sensitive = bool(required_uses & SENSITIVE_USES)
    if (
        not request_is_sensitive
        and _resolve_include_fulltext(include_fulltext, settings)
        and fulltext_top_k > 0
    ):
        selected_sources = {_parent_source_id(item[0]) for item in selected}
        fulltext_items = _fulltext_pool(
            intents,
            required_uses,
            evidence_class_filter,
            min_quality_score,
            keyword_weight,
            vector_weight,
            top_n=fulltext_top_k,
        )
        for item in fulltext_items:
            # Prefer passage-level fulltext from sources not already covered, so
            # the reference list gains quotable depth instead of duplicates.
            if _parent_source_id(item[0]) in selected_sources:
                continue
            selected.append(item)
            selected_sources.add(_parent_source_id(item[0]))

    return RetrievalResult(
        evidence=[_chunk_to_evidence(chunk, used_for, score) for chunk, score, used_for in selected]
    )
