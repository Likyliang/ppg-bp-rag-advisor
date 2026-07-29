"""Screening-suggestion evaluation / calibration harness.

Given a labeled case set, run the screening engine end-to-end and report, per
condition, the confusion matrix and sensitivity / specificity / precision —
i.e. "does the current `config/screening_rules.yaml` fire on the cases it
should, and stay quiet otherwise?". Also offers a per-feature threshold sweep
to suggest tuned cutoffs once real labeled data (ECG / echo / PSG / PWV) exists.

This measures *screening trigger behaviour against labels*, NOT diagnostic
truth — the suggestions remain hedged, referral-bearing, non-diagnostic.

Case file (JSONL), one object per line:
  {"id": "...", "payload": {<measurement payload incl. enable_screening_suggestions>},
   "expected_conditions": ["arrhythmia_screening", ...]}  # conditions that SHOULD fire

Usage:
  python scripts/evaluate_screening.py --cases tests/fixtures/screening_eval_cases.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.config_loader import resolve_project_path
from app.services.rule_engine import run_rule_engine
from app.services.safety import review_screening_suggestions
from app.services.screening import run_screening
from app.services.validator import parse_payload


DEFAULT_CASES = "tests/fixtures/screening_eval_cases.jsonl"


def _load_cases(path: str) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    case_path = resolve_project_path(path)
    with case_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def fired_conditions(payload_dict: Dict[str, Any]) -> List[str]:
    """Condition ids that the (safety-validated) screening engine emits."""
    payload = parse_payload(payload_dict)
    rule_result = run_rule_engine(payload)
    result = review_screening_suggestions(run_screening(payload, rule_result))
    return [s.condition_id for s in result.suggestions]


def _metrics(tp: int, fp: int, fn: int, tn: int) -> Dict[str, float]:
    sens = tp / (tp + fn) if (tp + fn) else None        # recall / true-positive rate
    spec = tn / (tn + fp) if (tn + fp) else None        # true-negative rate
    prec = tp / (tp + fp) if (tp + fp) else None        # positive predictive value
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "sensitivity": round(sens, 3) if sens is not None else None,
        "specificity": round(spec, 3) if spec is not None else None,
        "precision": round(prec, 3) if prec is not None else None,
    }


def evaluate_screening_cases(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-condition confusion matrix + metrics over the labeled cases."""
    all_conditions = set()
    case_results = []
    for case in cases:
        fired = set(fired_conditions(case["payload"]))
        expected = set(case.get("expected_conditions", []))
        all_conditions |= fired | expected
        case_results.append({"id": case.get("id"), "fired": sorted(fired), "expected": sorted(expected)})

    per_condition: Dict[str, Dict[str, Any]] = {}
    for condition in sorted(all_conditions):
        tp = fp = fn = tn = 0
        for cr in case_results:
            in_fired = condition in cr["fired"]
            in_expected = condition in cr["expected"]
            if in_fired and in_expected:
                tp += 1
            elif in_fired and not in_expected:
                fp += 1
            elif not in_fired and in_expected:
                fn += 1
            else:
                tn += 1
        per_condition[condition] = _metrics(tp, fp, fn, tn)

    # Macro averages over conditions that have a defined value.
    def _macro(key: str) -> Optional[float]:
        vals = [m[key] for m in per_condition.values() if m[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    exact = sum(1 for cr in case_results if set(cr["fired"]) == set(cr["expected"]))
    return {
        "case_count": len(cases),
        "exact_match_rate": round(exact / len(cases), 3) if cases else None,
        "macro_sensitivity": _macro("sensitivity"),
        "macro_specificity": _macro("specificity"),
        "macro_precision": _macro("precision"),
        "per_condition": per_condition,
        "cases": case_results,
    }


def _dig(payload: Dict[str, Any], dotted: str) -> Optional[float]:
    """Read a possibly-nested numeric feature like 'rhythm.ibi_cv'."""
    node: Any = payload
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, (int, float)) else None


def sweep_threshold(
    cases: List[Dict[str, Any]],
    feature_path: str,
    condition: str,
    candidates: List[float],
) -> Dict[str, Any]:
    """Sweep ``>=`` thresholds on one feature against the per-case labels.

    Label per case = whether ``condition`` is in expected_conditions. Reports
    sensitivity/specificity/Youden's J at each candidate so a cutoff can be
    chosen from real labeled data without re-running the whole engine.
    """
    pairs = []  # (feature_value, is_positive)
    for case in cases:
        value = _dig(case["payload"], feature_path)
        if value is None:
            continue
        pairs.append((value, condition in set(case.get("expected_conditions", []))))

    rows = []
    best = None
    for thr in candidates:
        tp = sum(1 for v, pos in pairs if v >= thr and pos)
        fp = sum(1 for v, pos in pairs if v >= thr and not pos)
        fn = sum(1 for v, pos in pairs if v < thr and pos)
        tn = sum(1 for v, pos in pairs if v < thr and not pos)
        m = _metrics(tp, fp, fn, tn)
        youden = None
        if m["sensitivity"] is not None and m["specificity"] is not None:
            youden = round(m["sensitivity"] + m["specificity"] - 1, 3)
        row = {"threshold": thr, **m, "youden_j": youden}
        rows.append(row)
        if youden is not None and (best is None or youden > best["youden_j"]):
            best = row
    return {
        "feature": feature_path,
        "condition": condition,
        "n_labeled": len(pairs),
        "suggested_threshold": best["threshold"] if best else None,
        "sweep": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate / calibrate screening suggestions against labeled cases.")
    parser.add_argument("--cases", default=DEFAULT_CASES, help="Labeled cases JSONL path.")
    parser.add_argument("--output", default=None, help="Optional JSON output path.")
    args = parser.parse_args()

    cases = _load_cases(args.cases)
    report = evaluate_screening_cases(cases)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        out = resolve_project_path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
