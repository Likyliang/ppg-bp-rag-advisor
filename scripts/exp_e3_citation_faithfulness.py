"""E3: sentence-level citation faithfulness of generated reports.

Upgrades the citation metric from "the [n] is in range" to "the cited evidence
semantically supports the sentence". For each report we split sentences, keep
those carrying a medical assertion, and for each cited sentence ask an
independent (异家族 GPT-5.5) judge whether the cited chunk(s) support it:
fully / partial / not_supported, plus whether the sentence NEEDS a citation
(for citation recall).

Outputs preliminary numbers (citation precision/recall, sentence-level
supported rate). They are PRELIMINARY until the 200-pair human calibration
(test-retest κ + Rogan–Gladen misclassification correction) is done — that
human step is the only thing standing between these and a defensible claim, and
it is intentionally left out of this no-human run. All judge calls go through
the shared rate limiter; the run is resumable (checkpointed per report).

Input: report bodies produced by E2 (knowledge_base/processed/e2_reports.jsonl,
each row {case_id, system, markdown, references:[{number,...,snippet}]}).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Dict, List, Optional

import requests

from app.services.chunking import split_sentences
from app.services.citations import INLINE_CITE_RE, extract_citation_numbers
from app.services.config_loader import load_eval_llm_config, resolve_project_path
from scripts.relevance_judge import _throttle  # reuse the judge rate limiter

REPORTS_PATH = "knowledge_base/processed/e2_reports.jsonl"
RESULT_PATH = "knowledge_base/processed/e3_citation_faithfulness.json"
DETAIL_PATH = "knowledge_base/processed/e3_sentence_judgements.jsonl"

# A sentence carries a medical assertion worth citing if it makes a factual /
# recommendation claim. Disclaimer / meta sentences are excluded from both
# numerator and denominator.
_NON_ASSERTION_MARKERS = (
    "本报告", "免责声明", "仅供", "不能替代", "参考文献", "参考依据",
    "以上内容", "如有不适", "祝您", "感谢",
)


class _JudgeError(RuntimeError):
    pass


SUPPORT_SYSTEM = (
    "你是医学引用核查员。给定一个来自健康报告的句子，以及它引用的若干条知识库证据片段，"
    "判断这些证据是否在语义上支持该句子的事实/建议内容。只输出 JSON：\n"
    '{"support": "fully|partial|not_supported", "needs_citation": true|false, "reason": "一句话"}\n'
    "support: fully=证据完整支持该句核心断言; partial=部分支持或仅沾边; not_supported=证据不支持或无关。\n"
    "needs_citation: 该句是否包含需要循证支持的医学事实或建议（纯安慰语/操作提示/免责声明为 false）。"
    "严格按证据内容判断，不要凭常识补足。"
)


_PROSE_RE = re.compile(r"[一-鿿A-Za-z]")
_CITE_MARKER_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def _is_assertion(sentence: str) -> bool:
    sentence = sentence.strip()
    if len(sentence) < 6:
        return False
    if sentence.lstrip().startswith("#"):  # markdown headings are not assertions
        return False
    # Reject units that carry no actual prose once citation markers / list
    # bullets / digits / punctuation are removed — e.g. a stray "[1,2,3]" split
    # off a heading. Such a unit makes no claim; judging it always yields
    # not_supported and would falsely depress citation precision.
    stripped = _CITE_MARKER_RE.sub("", sentence)
    if not _PROSE_RE.search(stripped):
        return False
    return not any(marker in sentence for marker in _NON_ASSERTION_MARKERS)


def _split_body_from_tail(markdown: str) -> str:
    """Drop the 参考文献/参考依据/免责声明 tail; judge only the body sentences."""
    for marker in ("## 参考文献", "## 参考依据说明", "## 免责声明"):
        idx = markdown.find(marker)
        if idx >= 0:
            markdown = markdown[:idx]
    return markdown


def _reference_snippets(references: List[Dict]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for ref in references or []:
        num = ref.get("number")
        if num is not None:
            out[int(num)] = (ref.get("snippet") or ref.get("title") or "")[:600]
    return out


def _judge_support(sentence: str, cited_snippets: List[str]) -> Dict[str, object]:
    cfg = load_eval_llm_config()
    if cfg.api_key and cfg.base_url:
        api_key, base_url, model = cfg.api_key, cfg.base_url.rstrip("/"), cfg.model
    else:
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    if not api_key:
        raise _JudgeError("no judge provider configured (EVAL_LLM_* or DEEPSEEK_API_KEY)")
    user = json.dumps(
        {"sentence": sentence, "cited_evidence": cited_snippets},
        ensure_ascii=False,
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SUPPORT_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": 150,
    }
    last_err = None
    for attempt in range(3):
        try:
            _throttle()
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=float(os.getenv("EVAL_LLM_TIMEOUT_SEC", "60")),
            )
            if resp.status_code >= 400:
                raise _JudgeError(f"HTTP {resp.status_code}: {resp.text[:160]}")
            content = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", content, re.S)
            obj = json.loads(match.group(0)) if match else {}
            support = obj.get("support")
            if support not in {"fully", "partial", "not_supported"}:
                support = "not_supported"
            return {
                "support": support,
                "needs_citation": bool(obj.get("needs_citation", True)),
                "reason": str(obj.get("reason", ""))[:160],
                "judge_model": model,
            }
        except (requests.RequestException, _JudgeError, KeyError, ValueError, IndexError) as exc:
            last_err = exc
            if attempt < 2:
                time.sleep(min(2**attempt, 6))
    raise _JudgeError(f"judge failed: {last_err}")


def _extract_sentence_units(markdown: str) -> List[Dict]:
    """Return assertion sentences with their inline citation numbers."""
    body = _split_body_from_tail(markdown)
    units = []
    for sent in split_sentences(body):
        if not _is_assertion(sent):
            continue
        nums = extract_citation_numbers(sent)
        units.append({"sentence": sent, "cited": nums})
    return units


def _load_done() -> Dict[str, Dict]:
    path = resolve_project_path(DETAIL_PATH)
    if not path.exists():
        return {}
    done = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                done[row["key"]] = row
    return done


def run_e3(
    limit_reports: Optional[int] = None,
    resume: bool = True,
    cited_only: bool = True,
    recall_sample: int = 0,
    concurrency: int = 3,
) -> Dict:
    """Judge sentence-level citation support.

    cited_only=True (default): judge ONLY sentences that carry an inline [n]
    (the citation-PRECISION metric + the S2-vs-S3 enforcement contrast). This
    is ~800 calls instead of ~7000, sparing the small judge endpoint. To also
    estimate citation RECALL, set recall_sample>0 to additionally judge a random
    sample of uncited assertion sentences for `needs_citation`.
    """
    import random
    from concurrent.futures import ThreadPoolExecutor

    reports_path = resolve_project_path(REPORTS_PATH)
    if not reports_path.exists():
        raise FileNotFoundError(f"{reports_path} not found — run E2 (evaluate_reports --real) first.")
    reports = [json.loads(l) for l in reports_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit_reports:
        reports = reports[:limit_reports]

    done = _load_done() if resume else {}

    # Build the task list (cited sentences always; a recall sample of uncited).
    tasks: List[Dict] = []
    uncited_pool: List[Dict] = []
    for report in reports:
        case_id = report.get("case_id", "case")
        system = report.get("system", "?")
        snippets = _reference_snippets(report.get("references", []))
        for si, unit in enumerate(_extract_sentence_units(report.get("markdown", ""))):
            key = f"{system}::{case_id}::{si}"
            if key in done:
                continue
            cited_snippets = [snippets[n] for n in unit["cited"] if n in snippets]
            task = {"key": key, "system": system, "case_id": case_id,
                    "sentence": unit["sentence"], "cited": unit["cited"], "snippets": cited_snippets}
            if unit["cited"] and cited_snippets:
                tasks.append(task)
            elif not cited_only:
                tasks.append(task)
            else:
                uncited_pool.append(task)
    if cited_only and recall_sample > 0 and uncited_pool:
        rng = random.Random(13)
        tasks.extend(rng.sample(uncited_pool, min(recall_sample, len(uncited_pool))))

    detail_path = resolve_project_path(DETAIL_PATH)
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    detail_handle = detail_path.open("a", encoding="utf-8")
    write_lock = __import__("threading").Lock()
    judgements: List[Dict] = list(done.values())

    def _do(task: Dict) -> Dict:
        try:
            verdict = _judge_support(task["sentence"], task["snippets"])
            if not task["cited"]:
                verdict["support"] = "no_citation"
        except _JudgeError as exc:
            verdict = {"support": None, "needs_citation": None, "reason": str(exc)[:120], "judge_model": None}
        row = {"key": task["key"], "system": task["system"], "case_id": task["case_id"],
               "sentence": task["sentence"], "cited": task["cited"], **verdict}
        with write_lock:
            detail_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            detail_handle.flush()
        return row

    try:
        if concurrency <= 1:
            judgements.extend(_do(t) for t in tasks)
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                judgements.extend(executor.map(_do, tasks))
    finally:
        detail_handle.close()

    return _summarize_e3(judgements)


def _summarize_e3(judgements: List[Dict]) -> Dict:
    from scripts.stat_utils import cluster_bootstrap_rate_ci

    by_system: Dict[str, List[Dict]] = {}
    for row in judgements:
        by_system.setdefault(row["system"], []).append(row)

    summary = {}
    for system, rows in by_system.items():
        cited = [r for r in rows if r["cited"] and r.get("support") in {"fully", "partial", "not_supported"}]
        # citation precision: of cited sentences, fraction fully supported
        fully = sum(1 for r in cited if r["support"] == "fully")
        partial = sum(1 for r in cited if r["support"] == "partial")
        # citation recall: of sentences that need a citation, fraction that have >=1 cite
        need = [r for r in rows if r.get("needs_citation")]
        need_with_cite = sum(1 for r in need if r["cited"])
        # cluster bootstrap on supported (1=fully) per report
        per_report: Dict[str, List[float]] = {}
        for r in cited:
            per_report.setdefault(r["case_id"], []).append(1.0 if r["support"] == "fully" else 0.0)
        lo, hi = cluster_bootstrap_rate_ci(list(per_report.values()), iters=5000, seed=13) if per_report else (0.0, 0.0)
        summary[system] = {
            "cited_sentences": len(cited),
            "citation_precision_strict": round(fully / len(cited), 4) if cited else None,
            "citation_precision_lenient": round((fully + 0.5 * partial) / len(cited), 4) if cited else None,
            "citation_recall": round(need_with_cite / len(need), 4) if need else None,
            "supported_rate_ci95": [round(lo, 4), round(hi, 4)],
            "needs_citation_sentences": len(need),
        }
    result = {
        "status": "PRELIMINARY",
        "caveat": "Judge-only (GPT-5.5). NOT human-calibrated: 200-pair κ + Rogan-Gladen correction pending. Do not report as final.",
        "judge_model": next((r.get("judge_model") for r in judgements if r.get("judge_model")), None),
        "total_judged": len([r for r in judgements if r.get("support")]),
        "by_system": summary,
    }
    out_path = resolve_project_path(RESULT_PATH)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["result_path"] = str(out_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="E3 sentence-level citation faithfulness (preliminary, judge-only).")
    parser.add_argument("--limit-reports", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--all-sentences", action="store_true",
                        help="Judge every assertion sentence (~7k calls). Default: cited sentences only (~800).")
    parser.add_argument("--recall-sample", type=int, default=0,
                        help="Additionally judge N random uncited sentences for needs_citation (recall estimate).")
    parser.add_argument("--concurrency", type=int, default=3, help="Judge worker threads (gentle on the endpoint).")
    args = parser.parse_args()
    result = run_e3(
        limit_reports=args.limit_reports,
        resume=not args.no_resume,
        cited_only=not args.all_sentences,
        recall_sample=args.recall_sample,
        concurrency=args.concurrency,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
