from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable, List

import requests

from app.schemas.measurement import MeasurementPayload
from app.schemas.report import Evidence
from app.schemas.rule_result import RuleResult


class LlmGenerationError(RuntimeError):
    pass


def _compact_evidence(evidence: Iterable[Evidence]) -> List[dict[str, Any]]:
    compact = []
    for item in evidence:
        compact.append(
            {
                "source_id": item.source_id,
                "title": item.title,
                "organization": item.organization,
                "region": item.region,
                "evidence_class": item.evidence_class,
                "allowed_uses": item.allowed_uses,
                "snippet": item.snippet,
            }
        )
    return compact


def _clean_markdown(markdown: str) -> str:
    markdown = markdown.strip()
    markdown = re.sub(r"\A```(?:markdown)?\s*", "", markdown)
    markdown = re.sub(r"\s*```\s*\Z", "", markdown)
    return markdown.strip()


def _deepseek_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def generate_deepseek_report_body(
    *,
    template_body: str,
    rule_result: RuleResult,
    evidence: Iterable[Evidence],
    rag_enabled: bool = True,
    timeout_sec: float | None = None,
) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        raise LlmGenerationError("DEEPSEEK_API_KEY is not set")

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    timeout = timeout_sec or float(os.getenv("LLM_TIMEOUT_SEC", "30"))

    system_prompt = (
        "你是一个医学安全约束 RAG 报告写作器。"
        "面向中国大陆普通小程序用户写作，语言要像耐心的健康助手：温和、清楚、有行动感。"
        "可以有一点关照感，例如先提醒用户别急着给自己下结论，再告诉他下一步怎么做。"
        "只能在给定规则结果、证据摘要和模板报告范围内改写。"
        "不得诊断、不得开药、不得调药、不得停药、不得承诺 PPG 准确性，"
        "不得声称可替代规范袖带血压测量或医生判断。"
        "不要新增参考来源，不要编造指南，不要删除 PPG 局限和免责声明语义。"
        "不要使用“无需紧急处理”“不属于紧急情况”“不视为紧急情况”“未触发本系统急症提醒规则”等规则或安抚性表述；"
        "如果没有急症相关症状，面向用户写成“目前没有填写胸痛、气短、肢体无力、视物改变、说话困难或严重头痛等需要立刻处理的症状；如果之后出现这些不适，请直接拨打 120 或前往急诊”。"
        "不要使用“确诊”这个词；需要表达时说“不是诊断结果”。"
        "即使是否定句，也不要出现停药、加药、减药、调药、服药等用药操作词；"
        "只说“用药问题请咨询医生”。"
        "不要把血压计写成诊断工具，只能写成复核和家庭记录工具。"
        "不要新增模板中没有的具体运动频次、测量频次、盐摄入量、药物剂量、治疗阈值或袖带厘米/指宽等操作细节。"
        "不要写 ≥140/90、<130/80、连续3天、3~5天、每天、每天早晚、早起后、晚饭前、睡前、袖带下缘2~3厘米、能插入1~2指等新细节；"
        "若要表达，只能说“按说明书规范测量”“连续记录”“带记录咨询医生”。"
        "中国本地化表达优先使用：社区卫生服务中心、乡镇卫生院、家庭医生团队、医院门诊、120、急诊。"
        "不要在用户正文里写“本报告参考了”“优先参考”“中国大陆常见健康管理语境”等来源说明，"
        "来源只由系统在参考来源区展示。"
        "避免把参考范围写成确诊标签；可以说“明显偏高参考范围”，并说明不等于诊断。"
        "不要输出内部字段名、英文枚举值、规则编号、CN_stage、stage_2_reference_range、RAG、检索、chunk、向量等开发词。"
    )
    if not rag_enabled:
        system_prompt += (
            "当前任务是非 RAG 对照组：不要声称参考了文档库、指南库或检索证据，"
            "不要输出参考来源；只能根据结构化输入做一般性、保守解释。"
        )
    user_payload = {
        "task": (
            "请把 template_body 改写成更像用户个性化健康解释报告的中文 Markdown。"
            "直接从第一个 Markdown 标题开始，不要写“好的”“以下是”“根据规则和输入信息”等开场白。"
            "保留相同标题结构，不输出参考来源、参考依据说明或免责声明章节；这些会由系统本地拼接。"
            "报告要像真实健康小程序面向用户的说明，不要暴露规则名、枚举值、模型字段或工程实现。"
            "文字要比模板更有人味：少用机械罗列，多用短句解释“为什么”和“下一步”。"
            "不要为了显得专业而新增具体阈值、测量频次、厘米数、指宽、运动频次或盐摄入量。"
            "保留或补充“## 现在最该做什么”“## 在国内可以怎么做”和“## 几个容易误解的点”章节。"
            "“现在最该做什么”必须像结论：直接说明本次属于什么情况、今天先做什么、什么情况下去哪里咨询。"
            "易懂解释要解释 PPG 是什么、为什么要用上臂式血压计复核、用户下一步怎么做，"
            "并把下一步落到中国大陆常见基层/门诊沟通路径。"
            "建议必须保持保守、可复测、可就医沟通，不提供诊断或治疗方案。"
        ),
        "rule_result": rule_result.model_dump(),
        "rag_enabled": rag_enabled,
        "evidence": _compact_evidence(evidence) if rag_enabled else [],
        "template_body": template_body,
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "max_tokens": 1800,
    }

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=_deepseek_headers(api_key),
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise LlmGenerationError(f"DeepSeek request failed: {exc.__class__.__name__}") from exc

    if response.status_code >= 400:
        detail = response.text[:500]
        raise LlmGenerationError(f"DeepSeek API returned HTTP {response.status_code}: {detail}")

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LlmGenerationError("DeepSeek API response did not contain message content") from exc

    cleaned = _clean_markdown(content)
    if not cleaned:
        raise LlmGenerationError("DeepSeek API returned empty content")
    return cleaned


def generate_deepseek_input_only_report(
    *,
    payload: MeasurementPayload,
    timeout_sec: float | None = None,
) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        raise LlmGenerationError("DEEPSEEK_API_KEY is not set")

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    timeout = timeout_sec or float(os.getenv("LLM_TIMEOUT_SEC", "30"))

    system_prompt = (
        "你是中文健康小程序里的健康说明助手。"
        "只根据用户提交的结构化输入写报告，不使用本地文档库、检索证据、规则模板或参考来源。"
        "不要声称参考了指南、文档库、知识库、检索结果或任何外部资料，不要列参考来源。"
        "医学安全底线必须保留：不得诊断、不得开药、不得调药、不得停药、不得承诺 PPG 准确性，"
        "不得声称可替代规范袖带血压测量或医生判断。"
        "如果输入里有胸痛、气短、肢体无力、视物改变、说话困难、严重头痛等症状，"
        "应提示优先拨打 120 或前往急诊。"
        "即使是否定句，也不要出现停药、加药、减药、调药、服药等用药操作词；只说用药问题请咨询医生。"
        "直接输出 Markdown，不要写“好的”“以下是”“根据输入”等开场白。"
    )
    user_payload = {
        "task": (
            "请根据 structured_input 直接生成一份中文健康解释报告。"
            "这是非 RAG 对照组：不要使用证据、不要引用来源、不要提本地文档库。"
            "报告要面向普通用户，尽量自然，不必遵循 RAG 版模板；但建议包含："
            "先看结论、现在最该做什么、为什么这样提醒你、接下来怎么做、几个容易误解的点。"
            "如果信息不足，可以直接说明不确定性。"
        ),
        "structured_input": payload.model_dump(mode="json"),
    }
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0.7,
        "max_tokens": 1800,
    }

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=_deepseek_headers(api_key),
            json=request_payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise LlmGenerationError(f"DeepSeek request failed: {exc.__class__.__name__}") from exc

    if response.status_code >= 400:
        detail = response.text[:500]
        raise LlmGenerationError(f"DeepSeek API returned HTTP {response.status_code}: {detail}")

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LlmGenerationError("DeepSeek API response did not contain message content") from exc

    cleaned = _clean_markdown(content)
    if not cleaned:
        raise LlmGenerationError("DeepSeek API returned empty content")
    return cleaned
