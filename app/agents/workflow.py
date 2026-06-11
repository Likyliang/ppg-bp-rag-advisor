from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

from pydantic import ValidationError

from app.schemas.report import CitationQuality, HealthReport
from app.schemas.rule_result import RuleResult
from app.services.citations import extract_citation_numbers
from app.services.evidence_quality import evaluate_citation_quality
from app.services.generator import (
    generate_report_draft,
    generate_template_report,
    inject_screening_markdown,
)
from app.services.retriever import retrieve_knowledge
from app.services.rule_engine import run_rule_engine
from app.services.safety import apply_safety_edits, review_safety, review_screening_suggestions
from app.services.screening import aggregate_retrieval, run_screening
from app.services.validator import parse_payload


TAIL_CITATION_CLAIM = "正文中的 [n]"


def _citation_consistency_issue(report: HealthReport) -> Optional[str]:
    """Return a problem string if the report's inline citations are inconsistent.

    Guards the final invariant: when evidence exists and the tail claims the body
    uses [n] markers, the body must actually contain valid markers, and no inline
    number may exceed the evidence count. Returns None when consistent.
    """
    evidence_count = len(report.retrieved_evidence)
    if evidence_count == 0:
        return None
    body = report.markdown_report or ""
    # Only enforce when the tail advertises inline citations (RAG reports do).
    if TAIL_CITATION_CLAIM not in body:
        return None
    numbers = extract_citation_numbers(body)
    # Markers found include the reference list itself; restrict to the body part.
    body_only = body.split("## 参考文献", 1)[0]
    body_numbers = extract_citation_numbers(body_only)
    if not body_numbers:
        return "正文缺少内联引用，但尾部声明使用 [n] 标注。"
    over_range = [n for n in numbers if n > evidence_count or n < 1]
    if over_range:
        return f"正文引用编号超出证据数量（{evidence_count}）：{over_range}。"
    return None


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

    # Screening suggestions ("建议进一步排查"): opt-in, hedged, referral-bearing,
    # validated by the safety layer. Their retrieval intents are folded into the
    # evidence query so any cited screening line is backed by governed sources.
    screening = review_screening_suggestions(run_screening(payload, rule_result))
    screening_intents, screening_uses = aggregate_retrieval(screening)
    retrieval_intents = list(dict.fromkeys(rule_result.retrieval_intents + screening_intents))
    retrieval_allowed_uses = list(dict.fromkeys(rule_result.retrieval_allowed_uses + screening_uses))

    retrieval_result = retrieve_knowledge(
        retrieval_intents,
        allowed_uses=retrieval_allowed_uses,
        min_quality_score=18,
    )
    evidence = list(retrieval_result.evidence)

    # Dedicated screening-evidence pass: the report's top-k is dominated by BP
    # sources, so the governed SCG/research-background sources that back a
    # screening suggestion rarely survive. Retrieve them with the screening
    # intents and merge (dedup by source) so a suggestion can cite the exact
    # paper supporting its feature→condition association.
    if screening.produced and screening_intents:
        screening_evidence = retrieve_knowledge(
            screening_intents,
            allowed_uses=screening_uses or ["research_background"],
            min_quality_score=18,
            top_k=4,
        ).evidence
        seen_sources = {item.source_id for item in evidence}
        for item in screening_evidence:
            if item.source_id not in seen_sources:
                evidence.append(item)
                seen_sources.add(item.source_id)

    citation_quality = evaluate_citation_quality(rule_result, evidence)
    draft = generate_report_draft(
        payload=payload,
        rule_result=rule_result,
        evidence=evidence,
        mode=report_mode,
        warnings=retrieval_result.warnings + citation_quality.issues,
        citation_quality=citation_quality,
        screening=screening,
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
                screening=screening,
            )
            inject_screening_markdown(fallback)
            fallback.generation_mode = "llm_only_safety_fallback_template"
        else:
            fallback = generate_report_draft(
                payload=payload,
                rule_result=rule_result,
                evidence=evidence,
                mode="template_only",
                warnings=retrieval_result.warnings
                + citation_quality.issues
                + ["LLM 输出未通过安全审查，已回退到 template_only。"],
                citation_quality=citation_quality,
                screening=screening,
            )
            fallback.generation_mode = "llm_rag_safety_fallback_template"
        safety_review = review_safety(fallback, rule_result)
        return apply_safety_edits(fallback, safety_review)

    # Final citation-consistency guard: a RAG body whose tail promises inline
    # [n] must actually deliver valid, in-range markers. The generator already
    # repairs DeepSeek/Claude output; this is the last line of defence so a
    # leaked inconsistency degrades safely to the template instead of shipping.
    if draft.generation_mode.startswith("llm_rag"):
        issue = _citation_consistency_issue(draft)
        if issue:
            fallback = generate_report_draft(
                payload=payload,
                rule_result=rule_result,
                evidence=evidence,
                mode="template_only",
                warnings=retrieval_result.warnings
                + citation_quality.issues
                + [f"LLM 输出引用一致性校验未通过，已回退到 template_only：{issue}"],
                citation_quality=citation_quality,
                screening=screening,
            )
            fallback.generation_mode = "llm_rag_citation_fallback_template"
            safety_review = review_safety(fallback, rule_result)
            return apply_safety_edits(fallback, safety_review)

    return apply_safety_edits(draft, safety_review)
