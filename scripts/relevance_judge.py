"""Independent LLM relevance judge for E1 pooled-qrels pre-labeling.

The judge labels query–chunk graded relevance (2/1/0). It must be independent
of the *retriever* (embeddings / keyword scoring) — which any chat LLM is — so
the qrels are not produced by the same mechanism being evaluated. For E1 the
generation family does not matter (there is no generation), so the judge may be
DeepSeek; E3 (citation faithfulness) has the stricter judge≠generator rule.

Provider resolution uses only the dedicated evaluation channel. Report LLM and
embedding credentials are never reused. Results are returned as ints with a
per-pair rationale so a human can review them.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

import requests

from app.services.config_loader import load_eval_llm_config


# Global rate limiter: a minimum interval between request *starts*, shared
# across threads. Protects a small/personal endpoint from bursts even when
# several judge workers run concurrently. Controlled by EVAL_LLM_MIN_INTERVAL_SEC
# (default 1.5s ≈ <=40 req/min); set 0 to disable.
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = [0.0]


def _throttle() -> None:
    min_interval = load_eval_llm_config().min_interval_sec
    if min_interval <= 0:
        return
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _LAST_REQUEST_AT[0] + min_interval - now
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_AT[0] = time.monotonic()


GRADE_SYSTEM = (
    "你是医学知识检索的相关性标注员。给定一个用户查询和一段知识库文本，"
    "判断这段文本对回答该查询的相关程度，只输出一个 JSON 对象。"
    "分级标准（graded relevance）：\n"
    "2 = 直接相关：文本直接支持该查询所需的核心信息或建议用途；\n"
    "1 = 部分相关：主题相关但不足以独立支撑该查询的核心需求；\n"
    "0 = 不相关：主题不符或无助于该查询。\n"
    "严格按事实判断，不要因为文本来自权威机构就抬高分数。"
    '只输出 JSON：{"grade": 2|1|0, "reason": "一句话理由"}'
)


class RelevanceJudgeError(RuntimeError):
    pass


def _resolve_provider() -> Tuple[str, str, str, str]:
    """Return (provider_label, api_key, base_url, model)."""
    eval_cfg = load_eval_llm_config()
    if eval_cfg.api_key and eval_cfg.base_url:
        return ("eval_llm", eval_cfg.api_key, eval_cfg.base_url.rstrip("/"), eval_cfg.model)
    raise RelevanceJudgeError(
        "No dedicated evaluation judge is configured. Report-generation keys are never reused."
    )


def judge_provider_label() -> str:
    return _resolve_provider()[0]


def _parse_grade(content: str) -> Tuple[int, str]:
    match = re.search(r"\{.*\}", content, re.S)
    if match:
        try:
            obj = json.loads(match.group(0))
            grade = int(obj.get("grade"))
            if grade in (0, 1, 2):
                return grade, str(obj.get("reason", ""))[:200]
        except (ValueError, TypeError):
            pass
    # Fallback: a bare digit.
    digit = re.search(r"\b([012])\b", content)
    if digit:
        return int(digit.group(1)), "parsed_from_text"
    raise RelevanceJudgeError(f"Could not parse grade from judge output: {content[:120]!r}")


def grade_pair(
    query: str,
    chunk_text: str,
    *,
    timeout_sec: Optional[float] = None,
    max_retries: int = 2,
) -> Dict[str, object]:
    """Grade one (query, chunk) pair. Returns {grade, reason, judge_model}."""
    provider, api_key, base_url, model = _resolve_provider()
    timeout = timeout_sec or load_eval_llm_config().timeout_sec
    user = json.dumps(
        {"query": query, "knowledge_text": chunk_text[:1200]},
        ensure_ascii=False,
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": GRADE_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": 120,
    }
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            _throttle()  # global rate limit before every request start
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
                allow_redirects=False,
            )
            if response.status_code >= 400:
                raise RelevanceJudgeError(f"judge HTTP {response.status_code}")
            content = response.json()["choices"][0]["message"]["content"]
            grade, reason = _parse_grade(content)
            return {"grade": grade, "reason": reason, "judge_model": model, "judge_provider": provider}
        except (requests.RequestException, RelevanceJudgeError, KeyError, IndexError) as exc:
            last_err = exc
            if attempt < max_retries:
                time.sleep(min(2**attempt, 6))
    raise RelevanceJudgeError(f"judge failed after {max_retries + 1} attempts: {last_err}")


__all__ = ["grade_pair", "judge_provider_label", "RelevanceJudgeError"]
