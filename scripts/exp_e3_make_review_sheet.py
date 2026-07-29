"""Build the human / cross-model calibration sheet for E3 citation faithfulness.

Stratified sample (system in {S2_enforced, S3_unenforced} x support in
{fully, partial, not_supported}) so Cohen's kappa is not swamped by the
majority `partial` class. S1/S4 carry no inline citations, so they are out of
scope for citation-support calibration.

For each judged cited sentence it reconstructs the cited EVIDENCE TEXT (from the
saved E2 reports, deterministic, no API) so an annotator can judge support
without trusting the judge. Outputs:

* e3_review_sheet.jsonl  — round-trippable; carries the hidden judge label +
  reason and blank `cc_label` / `codex_label` slots for the kappa computation.
* e3_review_sheet.md     — BLIND sheet (judge label/reason withheld) showing the
  sentence + cited evidence + a blank to fill, grouped by stratum.

High-risk sentences (numeric thresholds / medication / emergency / pregnancy /
diagnosis) are flagged `escalate=True` per paper-prep/114: any cross-annotator
disagreement on these must go to the author for sign-off.

Deterministic (seeded) so the selection is reproducible and auditable.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from typing import Dict, List

from app.services.config_loader import resolve_project_path
import scripts.exp_e3_citation_faithfulness as e3

JUDGE_PATH = "knowledge_base/processed/e3_sentence_judgements.jsonl"
REVIEW_JSONL = "knowledge_base/processed/e3_review_sheet.jsonl"
REVIEW_MD = "knowledge_base/processed/e3_review_sheet.md"

SUPPORT_CLASSES = ("fully", "partial", "not_supported")
CALIBRATION_SYSTEMS = ("S2_llm_rag_enforced", "S3_llm_rag_unenforced")

# High-risk semantics that force the escalation queue (paper-prep/114).
_HIGH_RISK = {
    "threshold": re.compile(r"\d{2,3}\s*/\s*\d{2,3}|\d{2,3}\s*mmHg|≥|>=|>\s*\d{2,3}|连续\s*\d+\s*[天次]"),
    "medication": re.compile(r"药|剂量|加量|减量|停药|降压药|服用"),
    "emergency": re.compile(r"急诊|120|急救|胸痛|卒中|中风|立即就医|尽快就医"),
    "pregnancy": re.compile(r"孕|妊娠|备孕"),
    "diagnosis": re.compile(r"确诊|诊断"),
}


def _high_risk_tags(sentence: str) -> List[str]:
    return [name for name, pat in _HIGH_RISK.items() if pat.search(sentence)]


def _report_ref_index() -> Dict[tuple, Dict[int, str]]:
    reports = [json.loads(l) for l in resolve_project_path(e3.REPORTS_PATH).read_text(encoding="utf-8").splitlines() if l.strip()]
    idx = {}
    for rep in reports:
        idx[(rep.get("system"), rep.get("case_id"))] = e3._reference_snippets(rep.get("references", []))
    return idx


def build_review_sheet(per_stratum: int = 34, seed: int = 13) -> Dict:
    judgements = [json.loads(l) for l in resolve_project_path(JUDGE_PATH).read_text(encoding="utf-8").splitlines() if l.strip()]
    ref_idx = _report_ref_index()
    rng = random.Random(seed)

    # group cited judgements into the 6 strata
    strata: Dict[tuple, List[Dict]] = defaultdict(list)
    for row in judgements:
        if row.get("system") not in CALIBRATION_SYSTEMS:
            continue
        if not row.get("cited") or row.get("support") not in SUPPORT_CLASSES:
            continue
        strata[(row["system"], row["support"])].append(row)

    selected: List[Dict] = []
    stratum_report = {}
    for system in CALIBRATION_SYSTEMS:
        for support in SUPPORT_CLASSES:
            group = strata.get((system, support), [])
            k = min(per_stratum, len(group))
            picks = rng.sample(group, k) if group else []
            stratum_report[f"{system}|{support}"] = {"available": len(group), "selected": k}
            for row in picks:
                snippets = ref_idx.get((row["system"], row["case_id"]), {})
                evidence = [{"n": n, "text": snippets.get(n, "[missing snippet]")} for n in row["cited"]]
                tags = _high_risk_tags(row["sentence"])
                selected.append({
                    "key": row["key"],
                    "system": row["system"],
                    "case_id": row["case_id"],
                    "stratum_support": support,         # = the JUDGE label (hidden in MD)
                    "sentence": row["sentence"],
                    "cited": row["cited"],
                    "evidence": evidence,
                    "judge_support": row["support"],
                    "judge_reason": row.get("reason", ""),
                    "high_risk_tags": tags,
                    "escalate": bool(tags),
                    "cc_label": "",
                    "codex_label": "",
                    "final_label": "",
                })

    rng.shuffle(selected)  # break stratum ordering so the blind sheet is unbiased
    for i, row in enumerate(selected):
        row["item_id"] = f"E3-{i:03d}"

    jsonl_path = resolve_project_path(REVIEW_JSONL)
    with jsonl_path.open("w", encoding="utf-8") as h:
        for row in selected:
            h.write(json.dumps(row, ensure_ascii=False) + "\n")

    md_path = resolve_project_path(REVIEW_MD)
    with md_path.open("w", encoding="utf-8") as h:
        h.write("# E3 句级引用忠实性 · 盲标清单\n\n")
        h.write("> 判定：**fully**=每个可检验断言都被引用证据可复验支持；**partial**=部分支持/缺关键可检验信息；"
                "**not_supported**=核心断言无证据或与证据冲突。\n")
        h.write("> 二级降级：含阈值/时点/指标/人群主张但证据缺该项 → partial 降级 not_supported。\n")
        h.write("> 在每条 `label:` 后填 fully / partial / not_supported。⚠️=高风险(需作者签字)。judge 标签与理由已隐藏以保盲标。\n\n")
        h.write(f"共 {len(selected)} 条（{per_stratum}/层 × 6 层，S2/S3 × 3 支持级）。\n\n")
        for row in selected:
            flag = "⚠️ " if row["escalate"] else ""
            h.write(f"## {row['item_id']} {flag}[{row['system'].split('_')[0]} · {row['case_id']}]\n")
            if row["high_risk_tags"]:
                h.write(f"_高风险标签: {', '.join(row['high_risk_tags'])}_\n")
            h.write(f"\n**句子**: {row['sentence']}\n\n")
            h.write("**被引证据**:\n")
            for ev in row["evidence"]:
                h.write(f"- [{ev['n']}] {ev['text'][:400]}\n")
            h.write(f"\n`label:` ____\n\n")

    return {"selected": len(selected), "strata": stratum_report,
            "jsonl": str(jsonl_path), "md": str(md_path)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the E3 citation-faithfulness calibration sheet.")
    ap.add_argument("--per-stratum", type=int, default=34)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    print(json.dumps(build_review_sheet(per_stratum=args.per_stratum, seed=args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
