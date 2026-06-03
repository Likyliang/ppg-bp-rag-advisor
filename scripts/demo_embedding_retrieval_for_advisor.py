from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.fulltext_vector_index import query_hashing_vector_index
from app.services.retriever import infer_allowed_uses, retrieve_knowledge


DEFAULT_QUERIES = [
    "手机PPG估算血压为什么不能替代上臂式血压计？",
    "低质量PPG信号下，用户应该如何复测和记录？",
    "如果血压估算很高并伴有胸痛，报告应该优先提示什么？",
    "连续几天家庭血压偏高，应该怎么记录并和医生沟通？",
]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "invalid_json", "path": str(path), "error": str(exc)}


def _short_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value[:5])
    if isinstance(value, set):
        return ", ".join(sorted(str(item) for item in value))
    return str(value or "")


def _keyword_rows(query: str, top_k: int) -> List[Dict[str, Any]]:
    result = retrieve_knowledge([query], top_k=top_k, min_quality_score=18)
    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(result.evidence, start=1):
        rows.append(
            {
                "rank": index,
                "score": item.score,
                "title": item.title,
                "source_id": item.source_id,
                "topic": item.topic,
                "region": item.region,
                "evidence_class": item.evidence_class,
                "allowed_uses": item.allowed_uses or [],
            }
        )
    return rows


def _vector_rows(query: str, top_k: int, show_snippets: bool) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        results = query_hashing_vector_index(query, top_k=top_k)
    except Exception as exc:
        return [{"status": "error", "message": f"{exc.__class__.__name__}: {exc}"}]
    if not results:
        return [{"status": "missing", "message": "本地全文向量文件不存在；可先运行 scripts/ingest_fulltext_pdfs.py 生成。"}]
    for index, item in enumerate(results, start=1):
        row = {
            "rank": index,
            "score": item.get("score"),
            "title": item.get("title"),
            "source_id": item.get("source_id"),
            "topic": item.get("topic"),
            "page": item.get("page_start"),
            "evidence_class": item.get("evidence_class"),
            "allowed_uses": item.get("allowed_uses") or [],
        }
        if show_snippets:
            content = " ".join(str(item.get("content") or "").split())
            row["snippet"] = content[:160] + ("..." if len(content) > 160 else "")
        rows.append(row)
    return rows


def _manifest_summary() -> Dict[str, Dict[str, Any]]:
    processed = PROJECT_ROOT / "knowledge_base" / "processed"
    return {
        "local_fulltext_hashing": _read_json(processed / "fulltext_vector_manifest.json"),
        "openai_processed_chunks": _read_json(processed / "openai_embedding_manifest_processed_chunks.json"),
        "openai_fulltext_chunks": _read_json(processed / "openai_embedding_manifest_fulltext_chunks.json"),
    }


def _manifest_line(name: str, data: Dict[str, Any]) -> str:
    if data.get("status") == "missing":
        return f"- {name}: manifest missing ({data.get('path')})"
    if data.get("backend") == "local_hashing_vectors":
        return (
            f"- {name}: {data.get('backend')}, {data.get('embedding_dims')}维, "
            f"{data.get('source_count')}个PDF来源, {data.get('page_count')}页, "
            f"{data.get('chunk_count')}条全文分块"
        )
    if data.get("backend") == "openai_embeddings":
        return (
            f"- {name}: {data.get('model_requested')}, {data.get('embedding_dimensions')}维, "
            f"{data.get('chunk_count')}条分块, {data.get('source_count')}个来源, "
            f"scope={data.get('scope')}"
        )
    return f"- {name}: {data.get('status', 'unknown')}"


def _table(rows: List[Dict[str, Any]], include_page: bool = False, show_snippets: bool = False) -> str:
    if rows and rows[0].get("status"):
        return f"> {rows[0].get('message', rows[0].get('status'))}\n"
    headers = ["rank", "score", "title", "topic", "region/class", "allowed_uses"]
    if include_page:
        headers.insert(4, "page")
    if show_snippets:
        headers.append("snippet")
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        region_class = " / ".join(
            part for part in [str(row.get("region") or ""), str(row.get("evidence_class") or "")] if part
        )
        values = [
            str(row.get("rank", "")),
            str(row.get("score", "")),
            str(row.get("title", ""))[:80],
            str(row.get("topic", "")),
            region_class,
            _short_list(row.get("allowed_uses")),
        ]
        if include_page:
            values.insert(4, str(row.get("page", "")))
        if show_snippets:
            values.append(str(row.get("snippet", "")).replace("|", " "))
        lines.append("| " + " | ".join(value.replace("\n", " ") for value in values) + " |")
    return "\n".join(lines) + "\n"


def build_markdown(queries: Iterable[str], top_k: int, show_snippets: bool) -> str:
    manifests = _manifest_summary()
    lines = [
        "# 导师汇报用：embedding 检索展示",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "- 分支定位：从 3ad8763 拉出的演示分支，只展示检索侧预研，不接入最新报告优化分支。",
        "- 展示边界：默认隐藏原文片段，只展示来源标题、主题、证据等级、用途标签和分数。",
        "",
        "## 当前索引状态",
        "",
    ]
    for name, data in manifests.items():
        lines.append(_manifest_line(name, data))
    lines.extend(
        [
            "",
            "## 查询演示",
            "",
            "每个问题同时展示两类结果：",
            "",
            "- 当前主链路：治理分块 + 关键词/用途标签/证据等级/质量分加权。",
            "- 本地全文向量：384维哈希向量，刻意不叠加安全过滤，用于展示 embedding 类检索的形态和潜在缺陷。",
            "",
        ]
    )
    for query in queries:
        inferred = infer_allowed_uses([query])
        lines.extend(
            [
                f"### {query}",
                "",
                f"- 推断用途标签：`{_short_list(inferred)}`",
                "",
                "**当前主链路结果**",
                "",
                _table(_keyword_rows(query, top_k), include_page=False, show_snippets=False),
                "",
                "**本地全文向量结果**",
                "",
                _table(_vector_rows(query, top_k, show_snippets), include_page=True, show_snippets=show_snippets),
                "",
            ]
        )
    lines.extend(
        [
            "## 汇报时可以主动暴露的缺陷",
            "",
            "- 纯向量命中有时更像“语义相似”，不一定自动满足医疗安全场景需要。",
            "- 对急症、用药、孕产妇等敏感问题，仍必须叠加用途标签、证据等级和高信任来源过滤。",
            "- 本地哈希向量不等价于真正语义 embedding，适合做离线演示和检索调试，不适合作为最终结论。",
            "- 急症问题可能被裸向量召回到生活方式或普通监测材料，这恰好可以说明安全过滤层仍然必要。",
            "- OpenAI embedding 试验已有索引规模，但现场查询需要 API key；因此本演示优先使用可离线展示的本地向量。",
            "",
            "## 汇报话术",
            "",
            "> 这周我把 embedding 检索侧做了一个演示分支：当前主链路仍以可解释检索和安全元数据过滤为主，embedding 主要作为候选证据召回的预研方向。它对英文专业文献和同义表达可能有帮助，但在医疗安全场景里不能单独使用，后续要继续比较命中稳定性、引用覆盖和敏感场景的安全过滤。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an advisor-facing retrieval demo report.")
    parser.add_argument("--query", action="append", help="Custom query. May be passed multiple times.")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--show-snippets", action="store_true", help="Include short text snippets in local, uncommitted output.")
    parser.add_argument("--output", default="outputs/advisor_embedding_demo/embedding_retrieval_demo.md")
    args = parser.parse_args()

    queries = args.query or DEFAULT_QUERIES
    markdown = build_markdown(queries, top_k=args.top_k, show_snippets=args.show_snippets)
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
