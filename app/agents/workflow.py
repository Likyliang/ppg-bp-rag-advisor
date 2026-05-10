from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

from pydantic import ValidationError

from app.schemas.report import HealthReport
from app.schemas.rule_result import RuleResult
from app.services.generator import generate_report_draft
from app.services.retriever import retrieve_knowledge
from app.services.rule_engine import run_rule_engine
from app.services.safety import apply_safety_edits, review_safety
from app.services.validator import parse_payload


def preview_rules(raw_payload: Mapping) -> RuleResult:
    payload = parse_payload(raw_payload)
    return run_rule_engine(payload)


def generate_report(raw_payload: Mapping, report_mode: Optional[str] = None) -> HealthReport:
    try:
        payload = parse_payload(raw_payload)
    except ValidationError:
        raise

    rule_result = run_rule_engine(payload)
    retrieval_result = retrieve_knowledge(rule_result.retrieval_intents)
    draft = generate_report_draft(
        payload=payload,
        rule_result=rule_result,
        evidence=retrieval_result.evidence,
        mode=report_mode,
        warnings=retrieval_result.warnings,
    )
    safety_review = review_safety(draft, rule_result)
    return apply_safety_edits(draft, safety_review)
