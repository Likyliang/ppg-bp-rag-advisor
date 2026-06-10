"""Build the human review sheet for E1 pooled qrels.

Sampling protocol (from the plan): review ALL pairs of sensitive queries
(emergency / medication / special-population) + a 30% random sample of the
non-sensitive pairs. The reviewer fills `human_grade` (0/1/2); blank rows keep
the judge grade. Outputs:

* a JSONL the evaluate step reads back (round-trippable: same schema as the
  pool, with a `selected_for_review` flag);
* a human-friendly Markdown sheet grouped by query, showing the judge grade +
  reason and a blank to fill, so review can happen in any editor.

Deterministic sampling (seeded) so the selection is reproducible and auditable.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from typing import Dict, List

from app.services.config_loader import resolve_project_path

POOL_PATH = "knowledge_base/processed/e1_qrels_pool.jsonl"
REVIEW_JSONL = "knowledge_base/processed/e1_review_sheet.jsonl"
REVIEW_MD = "knowledge_base/processed/e1_review_sheet.md"

GRADE_HINT = "2=直接相关 / 1=部分相关 / 0=不相关"


def _load_pool() -> List[Dict]:
    path = resolve_project_path(POOL_PATH)
    if not path.exists():
        raise FileNotFoundError(f"pool not found: {path} (run `exp_e1_retrieval_ablation pool` first)")
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_review_sheet(nonsensitive_fraction: float = 0.30, seed: int = 13) -> Dict:
    rows = _load_pool()
    rng = random.Random(seed)

    by_query: Dict[int, List[Dict]] = defaultdict(list)
    for row in rows:
        by_query[row["qid"]].append(row)

    selected: List[Dict] = []
    for qid, group in by_query.items():
        sensitive = any(r.get("sensitive") for r in group)
        if sensitive:
            for r in group:
                r["selected_for_review"] = True
            selected.extend(group)
        else:
            # 30% random sample of this query's pairs (at least 1 if any)
            k = max(1, round(len(group) * nonsensitive_fraction)) if group else 0
            picks = set(rng.sample(range(len(group)), min(k, len(group))))
            for i, r in enumerate(group):
                r["selected_for_review"] = i in picks
                if i in picks:
                    selected.append(r)

    # write round-trippable JSONL (full pool with flags + blank human_grade)
    jsonl_path = resolve_project_path(REVIEW_JSONL)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for r in rows:
            r.setdefault("human_grade", None)
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")

    # write human-friendly Markdown grouped by query
    md_lines: List[str] = [
        "# E1 相关性人工复核清单",
        "",
        f"> 复核口径：{GRADE_HINT}。在每条的 `human_grade:` 后填 0/1/2；留空则采用 judge 预标。",
        f"> 选样：敏感 query 全部 + 非敏感 {int(nonsensitive_fraction*100)}% 抽检（seed={seed}）。",
        f"> 共 {len(selected)} 条待复核（总池 {len(rows)} 对）。judge = GPT-5.5（独立于检索与生成）。",
        "",
    ]
    review_by_query: Dict[int, List[Dict]] = defaultdict(list)
    for r in selected:
        review_by_query[r["qid"]].append(r)

    for qid in sorted(review_by_query):
        group = review_by_query[qid]
        q = group[0]
        tag = "🔴敏感" if q.get("sensitive") else "常规"
        md_lines.append(f"## Q{qid} [{tag}] {q['query']}")
        md_lines.append(f"_预期用途: {', '.join(q['expected_uses'])}_")
        md_lines.append("")
        for r in sorted(group, key=lambda x: -(x.get("judge_grade") or 0)):
            jg = r.get("judge_grade")
            jg_str = str(jg) if jg is not None else "?"
            md_lines.append(f"- **[judge={jg_str}]** {r['title']}  ")
            md_lines.append(f"  片段: {(r.get('snippet') or '')[:160]}  ")
            md_lines.append(f"  judge 理由: {r.get('judge_reason', '')[:120]}  ")
            md_lines.append(f"  `chunk_id={r['chunk_id']}` `human_grade:` ____")
            md_lines.append("")
    md_path = resolve_project_path(REVIEW_MD)
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    judge_dist = defaultdict(int)
    for r in rows:
        judge_dist[r.get("judge_grade")] += 1
    return {
        "pool_pairs": len(rows),
        "selected_for_review": len(selected),
        "sensitive_pairs": sum(1 for r in rows if r.get("sensitive")),
        "judge_grade_distribution": {str(k): v for k, v in sorted(judge_dist.items(), key=lambda x: str(x[0]))},
        "review_jsonl": str(jsonl_path),
        "review_md": str(md_path),
    }


def apply_review_into_pool() -> Dict:
    """Copy human_grade from the review sheet back into the pool (after review)."""
    review_rows = []
    path = resolve_project_path(REVIEW_JSONL)
    with path.open("r", encoding="utf-8") as handle:
        review_rows = [json.loads(line) for line in handle if line.strip()]
    pool_path = resolve_project_path(POOL_PATH)
    with pool_path.open("w", encoding="utf-8") as handle:
        for r in review_rows:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
    filled = sum(1 for r in review_rows if r.get("human_grade") is not None)
    return {"rows": len(review_rows), "human_filled": filled, "pool_path": str(pool_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="E1 human review sheet builder / applier.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_make = sub.add_parser("make", help="Build review sheet (JSONL + Markdown).")
    p_make.add_argument("--fraction", type=float, default=0.30)
    p_make.add_argument("--seed", type=int, default=13)
    sub.add_parser("apply", help="After editing the review JSONL, write human_grade back into the pool.")
    args = parser.parse_args()
    if args.cmd == "make":
        print(json.dumps(build_review_sheet(args.fraction, args.seed), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(apply_review_into_pool(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
