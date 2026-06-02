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

    numbered_evidence = _number_evidence(evidence) if rag_enabled else []
    evidence_count = len(numbered_evidence)
    valid_numbers = "、".join(f"[{i}]" for i in range(1, evidence_count + 1)) or "（无）"

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
    if rag_enabled:
        system_prompt += (
            "你会收到一份按编号排列的循证资料（evidence，字段 citation_number）。"
            "这是硬性要求：正文必须在关键结论句、复测建议、设备复核、生活方式、PPG 局限说明、"
            "以及安全/急症提醒等句子末尾，用方括号编号标注引用，例如“家庭血压监测有助于判断趋势[2]”，"
            "需要时可合并标注为 [1,3]。"
            f"当前可用的合法编号只有：{valid_numbers}；只能引用这些真实存在的编号，"
            "绝对不能编造不存在的编号，也不能写超出范围的编号。"
            "尽量让每个有实质内容的小节都至少出现一次引用。"
            "不要自己写“参考文献”“参考来源”小节，也不要在正文里粘贴链接或 DOI；"
            "编号到具体文献的映射由系统统一拼接。"
        )
    else:
        system_prompt += (
            "当前任务是非 RAG 对照组：不要声称参考了文档库、指南库或检索证据，"
            "不要输出参考来源，正文中不要出现任何方括号编号引用；只能根据结构化输入做一般性、保守解释。"
        )
    user_payload = {
        "task": (
            "请把 template_body 改写成更像用户个性化健康解释报告的中文 Markdown。"
            "直接从第一个 Markdown 标题开始，不要写“好的”“以下是”“根据规则和输入信息”等开场白。"
            "保留相同标题结构，不输出参考来源、参考依据说明或免责声明章节；这些会由系统本地拼接。"
            "报告要像真实健康小程序面向用户的说明，不要暴露规则名、枚举值、模型字段或工程实现。"
            "文字要比模板更有人味：少用机械罗列，多用短句解释“为什么”和“下一步”。"
            "要结合本次具体输入（血压数值、心率、信号质量分、置信度、采集时长、年龄、症状、"
            "是否特殊人群、是否在用降压药、所在地区）写出有针对性的解释，避免空泛套话或只替换数字。"
            "不要为了显得专业而新增具体阈值、测量频次、厘米数、指宽、运动频次或盐摄入量。"
            "保留或补充“## 现在最该做什么”“## 在国内可以怎么做”和“## 几个容易误解的点”章节。"
            "“现在最该做什么”必须像结论：直接说明本次属于什么情况、今天先做什么、什么情况下去哪里咨询。"
            "易懂解释要解释 PPG 是什么、为什么要用上臂式血压计复核、用户下一步怎么做，"
            "并把下一步落到中国大陆常见基层/门诊沟通路径。"
            "建议必须保持保守、可复测、可就医沟通，不提供诊断或治疗方案。"
            + (
                "再次强调：正文关键句必须带上 evidence 的方括号编号引用，且只用给定的合法编号。"
                if rag_enabled
                else ""
            )
        ),
        "rule_result": rule_result.model_dump(),
        "rag_enabled": rag_enabled,
        "evidence": numbered_evidence,
        "template_body": template_body,
    }
    try:
        return _deepseek_chat(
            api_key=api_key,
            base_url=base_url,
            model=model,
            system_prompt=system_prompt,
            user_content=json.dumps(user_payload, ensure_ascii=False),
            timeout=timeout,
            temperature=0.2,
            max_tokens=1800,
        )
    except _DeepseekEmptyContent:
        # DeepSeek intermittently returns empty content. Retry once with a
        # shorter, more constrained prompt before giving up to fallback. The
        # retry still goes through the DeepSeek API (no other provider).
        retry_system, retry_user = _deepseek_retry_prompts(
            rule_result=rule_result,
            numbered_evidence=numbered_evidence,
            template_body=template_body,
            valid_numbers=valid_numbers,
            rag_enabled=rag_enabled,
        )
        return _deepseek_chat(
            api_key=api_key,
            base_url=base_url,
            model=model,
            system_prompt=retry_system,
            user_content=retry_user,
            timeout=timeout,
            temperature=0.3,
            max_tokens=1200,
        )


class _DeepseekEmptyContent(LlmGenerationError):
    """Raised when DeepSeek returns empty content, so callers can retry."""


def _deepseek_chat(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_content: str,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
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
        raise _DeepseekEmptyContent("DeepSeek API returned empty content")
    return cleaned


def _deepseek_retry_prompts(
    *,
    rule_result: RuleResult,
    numbered_evidence: List[dict[str, Any]],
    template_body: str,
    valid_numbers: str,
    rag_enabled: bool,
) -> tuple[str, str]:
    """Build a shorter, sturdier prompt for the empty-content retry.

    For low-quality / not-interpretable cases the report only needs to say:
    re-capture, verify with a cuffed upper-arm monitor, and do NOT interpret the
    blood-pressure range. We strip the long stylistic guidance to reduce the
    chance of another empty completion.
    """
    is_low_quality = (
        not rule_result.quality.is_usable
        or rule_result.estimated_bp_category == "not_interpretable_low_quality"
    )
    cite_clause = (
        f"正文关键句末尾必须用方括号编号引用，只能用这些合法编号：{valid_numbers}。"
        if rag_enabled and numbered_evidence
        else "正文中不要出现方括号编号引用。"
    )
    system = (
        "你是医学安全约束健康报告写作器，面向中国大陆普通用户，语言温和、简洁、清楚。"
        "硬性安全底线：不诊断、不开药/停药/调药、不承诺 PPG 准确、不把 PPG 或血压计说成可替代规范测量或医生判断。"
        "不要输出 RAG、chunk、向量、枚举值等工程词，不要写参考来源/免责声明小节。"
        "不要新增固定测量时点、睡眠小时数、连续几天/几周等具体细节；"
        "只说“按说明书规范测量”“在相对固定、方便的时间连续记录”“保持规律作息”“带记录咨询医生”。"
        + cite_clause
    )
    if is_low_quality:
        task = (
            "请生成一份简短的中文 Markdown 健康说明，重点是：本次信号质量不足，"
            "不解释血压高低，先重新规范采集，再用经过验证的上臂式电子血压计复核。"
            "包含小标题：## 先看结论、## 现在最该做什么、## 接下来怎么做、## 几个容易误解的点。"
            "直接从第一个 Markdown 标题开始，不要写开场白。"
        )
    else:
        task = (
            "请基于 rule_result 和 template_body 生成一份简短、个性化的中文 Markdown 健康说明，"
            "结合本次血压数值与信号质量给出有针对性的解释，保持保守、可复测、可就医沟通。"
            "保留 template_body 的小标题结构。直接从第一个 Markdown 标题开始，不要写开场白。"
        )
    user = json.dumps(
        {
            "task": task,
            "rule_result": rule_result.model_dump(),
            "evidence": numbered_evidence,
            "template_body": template_body,
        },
        ensure_ascii=False,
    )
    return system, user


def _number_evidence(evidence: Iterable[Evidence]) -> List[dict[str, Any]]:
    numbered = []
    for index, item in enumerate(evidence, start=1):
        numbered.append(
            {
                "citation_number": index,
                "title": item.title,
                "organization": item.organization,
                "region": item.region,
                "year": item.year,
                "evidence_class": item.evidence_class,
                "allowed_uses": item.allowed_uses,
                "snippet": item.snippet,
            }
        )
    return numbered


def _anthropic_chat(
    *, system: str, user: str, max_tokens: int, temperature: float, timeout: float
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise LlmGenerationError("ANTHROPIC_API_KEY is not set")

    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    try:
        response = requests.post(
            f"{base_url}/v1/messages", headers=headers, json=payload, timeout=timeout
        )
    except requests.RequestException as exc:
        raise LlmGenerationError(f"Anthropic request failed: {exc.__class__.__name__}") from exc
    if response.status_code >= 400:
        raise LlmGenerationError(
            f"Anthropic API returned HTTP {response.status_code}: {response.text[:500]}"
        )
    try:
        data = response.json()
        blocks = data["content"]
        content = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LlmGenerationError("Anthropic API response did not contain text content") from exc
    cleaned = _clean_markdown(content)
    if not cleaned:
        raise LlmGenerationError("Anthropic API returned empty content")
    return cleaned


_SAFETY_CONSTRAINTS = (
    "医学安全底线必须保留：不得诊断、不得开药、不得调药、不得停药、不得承诺 PPG 准确性，"
    "不得声称可替代规范袖带血压测量或医生判断。"
    "即使是否定句，也不要出现停药、加药、减药、调药、服药等用药操作词，只说\u201c用药问题请咨询医生\u201d。"
    "不要把血压计写成诊断工具，只能写成复核和家庭记录工具。"
    "不要使用\u201c确诊\u201d这个词；需要表达时说\u201c不是诊断结果\u201d。"
    "如果规则结果没有触发急症（emergency 为 false），可以说明目前没有需要立即处理的症状，"
    "但必须同时提示\u201c如果之后出现胸痛、气短、肢体无力、视物改变、说话困难或严重头痛，请立即拨打 120 或前往急诊\u201d。"
    "如果 emergency 为 true，必须把拨打 120 或前往急诊放在最前面，绝不能写任何\u201c不需要 120/急诊\u201d的安抚。"
)


def generate_anthropic_report_body(
    *,
    template_body: str,
    rule_result: RuleResult,
    evidence: Iterable[Evidence],
    rag_enabled: bool = True,
    timeout_sec: float | None = None,
) -> str:
    timeout = timeout_sec or float(os.getenv("LLM_TIMEOUT_SEC", "45"))
    numbered = _number_evidence(evidence) if rag_enabled else []
    system_prompt = (
        "你是一名严谨的中文健康科普写作者，面向中国大陆普通用户解释手机 PPG 血压估算结果。"
        "语言要专业、清晰、有条理，同时让普通人能读懂：先讲结论，再讲依据，最后讲下一步。"
        + _SAFETY_CONSTRAINTS
        + "你会收到一份按编号排列的循证资料（evidence）。"
        "请在正文相关结论或建议句末用方括号编号标注引用，例如\u201c家庭血压监测有助于判断趋势[2]\u201d；"
        "可以合并标注如[1,3]；只能引用 evidence 中真实存在的编号，不得编造编号或来源。"
        "不要自己写\u201c参考文献\u201d\u201c参考来源\u201d或免责声明小节，这些由系统统一附加。"
        "保留与模板相同的 Markdown 小标题结构（## 先看结论、## 现在最该做什么、## 为什么这样提醒你、"
        "## 怎么看这次测量、## 建议背后的原因、## 接下来怎么做、## 在国内可以怎么做、## 几个容易误解的点）。"
        "直接从第一个 Markdown 标题开始，不要写\u201c好的\u201d\u201c以下是\u201d等开场白。"
    )
    if not rag_enabled:
        system_prompt += "当前为非 RAG 模式：没有可引用的资料，正文中不要出现任何方括号编号引用。"
    user_payload = {
        "instruction": (
            "请基于 rule_result、evidence 与 template_body，重写出一份更专业、更具个性化的中文健康解释报告。"
            "要结合本次的具体数值、信号质量和用户背景给出有针对性的解释，避免空泛套话。"
        ),
        "rule_result": rule_result.model_dump(),
        "evidence": numbered,
        "template_body": template_body,
    }
    return _anthropic_chat(
        system=system_prompt,
        user=json.dumps(user_payload, ensure_ascii=False),
        max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "2400")),
        temperature=float(os.getenv("ANTHROPIC_TEMPERATURE", "0.4")),
        timeout=timeout,
    )


def generate_anthropic_input_only_report(
    *,
    payload: MeasurementPayload,
    timeout_sec: float | None = None,
) -> str:
    timeout = timeout_sec or float(os.getenv("LLM_TIMEOUT_SEC", "45"))
    system_prompt = (
        "你是中文健康小程序里的健康说明助手。只根据用户提交的结构化输入写报告，"
        "不使用本地文档库、检索证据或参考来源，也不要声称参考了任何指南或资料，不要列参考文献。"
        + _SAFETY_CONSTRAINTS
        + "直接输出 Markdown，不要写\u201c好的\u201d\u201c以下是\u201d等开场白。"
    )
    user_payload = {
        "instruction": (
            "请根据 structured_input 直接生成一份面向普通用户的中文健康解释报告。"
            "这是非 RAG 对照组：不要使用证据、不要引用来源、不要提本地文档库，也不要出现方括号编号引用。"
            "建议包含：先看结论、现在最该做什么、为什么这样提醒你、接下来怎么做、几个容易误解的点。"
        ),
        "structured_input": payload.model_dump(mode="json"),
    }
    return _anthropic_chat(
        system=system_prompt,
        user=json.dumps(user_payload, ensure_ascii=False),
        max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "2400")),
        temperature=float(os.getenv("ANTHROPIC_TEMPERATURE", "0.6")),
        timeout=timeout,
    )


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
