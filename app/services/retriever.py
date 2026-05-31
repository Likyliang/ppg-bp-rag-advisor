from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Set

from app.schemas.report import Evidence
from app.services.config_loader import resolve_project_path, load_yaml_config
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
BP_VALUE_RE = re.compile(r"\b\d{2,3}\s*[/／]\s*\d{2,3}\b")


@dataclass
class RetrievalResult:
    evidence: List[Evidence] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


@lru_cache(maxsize=8)
def _load_chunks_cached(path_string: str) -> tuple:
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
    return list(_load_chunks_cached(path_string))


def _score_chunk(query_tokens: Sequence[str], chunk: Dict) -> float:
    content = " ".join(
        str(chunk.get(field_name, ""))
        for field_name in ("title", "topic", "organization", "allowed_uses", "content")
    )
    chunk_tokens = _tokenize(content)
    if not query_tokens or not chunk_tokens:
        return 0.0

    query_set = set(query_tokens)
    chunk_set = set(chunk_tokens)
    overlap = len(query_set & chunk_set)
    if overlap == 0:
        return 0.0
    score = overlap / math.sqrt(len(query_set) * len(chunk_set))
    try:
        quality_boost = min(float(chunk.get("source_quality_score") or 0), 25) / 250
    except (TypeError, ValueError):
        quality_boost = 0.0
    return score + quality_boost


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


def _chunk_allowed(chunk: Dict, required_uses: Set[str], evidence_classes: Optional[Set[str]], min_quality_score: Optional[float]) -> bool:
    if chunk.get("review_status") == "excluded":
        return False
    if evidence_classes and chunk.get("evidence_class") not in evidence_classes:
        return False
    if min_quality_score is not None:
        try:
            if float(chunk.get("source_quality_score") or 0) < min_quality_score:
                return False
        except (TypeError, ValueError):
            return False
    if not required_uses:
        return True

    allowed_uses = set(_as_list(chunk.get("allowed_uses")))
    matched_uses = allowed_uses & required_uses
    if not matched_uses:
        return False

    sensitive = {"emergency_alert", "medication_safety", "special_population"} & matched_uses
    if sensitive and chunk.get("evidence_class") not in HIGH_TRUST_EVIDENCE_CLASSES:
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


def _select_with_use_coverage(ranked: List[tuple], required_uses: Set[str], limit: int) -> List[tuple]:
    selected = list(ranked[:limit])
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


def retrieve_knowledge(
    retrieval_intents: Iterable[str],
    top_k: int = None,
    chunks_path: str = None,
    allowed_uses: Iterable[str] = None,
    evidence_classes: Iterable[str] = None,
    min_quality_score: float = None,
) -> RetrievalResult:
    settings = load_yaml_config("config/settings.yaml").get("retrieval", {})
    limit = top_k or int(settings.get("top_k", 5))
    chunks = _load_chunks(chunks_path)
    if not chunks:
        return RetrievalResult(
            warnings=["知识库为空或尚未 ingest，已启用模板报告和规则兜底。"]
        )

    intents = list(retrieval_intents)
    required_uses = set(allowed_uses or []) or infer_allowed_uses(intents)
    evidence_class_filter = set(evidence_classes) if evidence_classes else None
    candidate_chunks = [
        chunk for chunk in chunks
        if _chunk_allowed(chunk, required_uses, evidence_class_filter, min_quality_score)
    ]
    if not candidate_chunks:
        candidate_chunks = [
            chunk for chunk in chunks
            if _chunk_allowed(chunk, set(), evidence_class_filter, min_quality_score)
        ]

    scored: Dict[str, tuple] = {}
    for intent in intents:
        query_tokens = _tokenize(intent)
        for chunk in candidate_chunks:
            base_score = _score_chunk(query_tokens, chunk)
            if base_score <= 0:
                continue
            score = _rerank_score(base_score, chunk, required_uses, intent)
            chunk_id = chunk.get("chunk_id") or f"{chunk.get('title', 'chunk')}-{len(scored)}"
            previous = scored.get(chunk_id)
            if previous is None or score > previous[1]:
                scored[chunk_id] = (chunk, score, intent)

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
    selected = _select_with_use_coverage(ranked, required_uses, limit)
    return RetrievalResult(
        evidence=[_chunk_to_evidence(chunk, used_for, score) for chunk, score, used_for in selected]
    )
