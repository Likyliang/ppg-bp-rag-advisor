from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

from pydantic import ValidationError

from app.schemas.report import CitationQuality, HealthReport
from app.schemas.rule_result import RuleResult
from app.services.evidence_quality import evaluate_citation_quality
from app.services.generator import generate_report_draft, generate_template_report
from app.services.retriever import retrieve_knowledge
from app.services.rule_engine import run_rule_engine
from app.services.safety import apply_safety_edits, review_safety
from app.services.validator import parse_payload


def preview_rules(raw_payload: Mapping) -> RuleResult:
    payload = parse_payload(raw_payload)
    return run_rule_engine(payload)


def _no_rag_citation_quality() -> CitationQuality:
    return CitationQuality(
        passed=False,
        coverage_rate=0.0,
        recommendation_grounding_rate=0.0,
        high_trust_sensitive_uses=False,
        issues=["非 RAG 对照组未使用文档库证据。"],
    )


def generate_report(raw_payload: Mapping, report_mode: Optional[str] = None) -> HealthReport:
    try:
        payload = parse_payload(raw_payload)
    except ValidationError:
        raise

    rule_result = run_rule_engine(payload)
    retrieval_result = retrieve_knowledge(
        rule_result.retrieval_intents,
        allowed_uses=rule_result.retrieval_allowed_uses,
        min_quality_score=18,
    )
    citation_quality = evaluate_citation_quality(rule_result, retrieval_result.evidence)
    draft = generate_report_draft(
        payload=payload,
        rule_result=rule_result,
        evidence=retrieval_result.evidence,
        mode=report_mode,
        warnings=retrieval_result.warnings + citation_quality.issues,
        citation_quality=citation_quality,
    )
    safety_review = review_safety(draft, rule_result)
    if not safety_review.passed and draft.generation_mode.startswith(("llm_rag", "llm_only")):
        if draft.generation_mode.startswith("llm_only"):
            fallback = generate_template_report(
                payload=payload,
                rule_result=rule_result,
                evidence=[],
                warnings=["非 RAG 对照组 LLM 输出未通过安全审查，已回退到无证据保守模板。"],
                citation_quality=_no_rag_citation_quality(),
                uses_rag=False,
            )
            fallback.generation_mode = "llm_only_safety_fallback_template"
        else:
            fallback = generate_report_draft(
                payload=payload,
                rule_result=rule_result,
                evidence=retrieval_result.evidence,
                mode="template_only",
                warnings=retrieval_result.warnings
                + citation_quality.issues
                + ["LLM 输出未通过安全审查，已回退到 template_only。"],
                citation_quality=citation_quality,
            )
            fallback.generation_mode = "llm_rag_safety_fallback_template"
        safety_review = review_safety(fallback, rule_result)
        return apply_safety_edits(fallback, safety_review)
    return apply_safety_edits(draft, safety_review)
