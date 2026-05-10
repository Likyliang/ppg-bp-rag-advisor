from __future__ import annotations

import json
from typing import Dict, List

from app.services.config_loader import resolve_project_path
from app.services.retriever import retrieve_knowledge
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES


GOLDEN_QUERIES: List[Dict] = [
    {"query": "PPG 血压估算准确吗 可以替代血压计吗", "expected_uses": ["cuffless_ppg_limitations"]},
    {"query": "无袖带 血压 设备 局限 PPG", "expected_uses": ["cuffless_ppg_limitations"]},
    {"query": "手指摄像头 PPG 信号质量差 怎么办", "expected_uses": ["signal_quality", "remeasurement"]},
    {"query": "置信度低 血压估算 是否可信", "expected_uses": ["signal_quality", "cuffless_ppg_limitations"]},
    {"query": "145/92 血压估算 偏高 需要注意什么", "expected_uses": ["bp_category_reference", "remeasurement"]},
    {"query": "130/85 估算血压 生活方式 建议", "expected_uses": ["bp_category_reference", "lifestyle"]},
    {"query": "185/122 胸痛 气短 需要急救吗", "expected_uses": ["emergency_alert"], "sensitive": True},
    {"query": "180 120 没有症状 复测 规范血压计", "expected_uses": ["bp_category_reference", "remeasurement"]},
    {"query": "胸痛 说话困难 肢体无力 高血压 急症", "expected_uses": ["emergency_alert"], "sensitive": True},
    {"query": "正在使用降压药 PPG 血压偏高 要停药吗", "expected_uses": ["medication_safety"], "sensitive": True},
    {"query": "降压药 剂量 调整 可以吗", "expected_uses": ["medication_safety"], "sensitive": True},
    {"query": "妊娠 孕妇 血压估算偏高", "expected_uses": ["special_population", "emergency_alert"], "sensitive": True},
    {"query": "糖尿病 用户 血压估算偏高 咨询医生", "expected_uses": ["special_population"]},
    {"query": "慢性肾病 CKD 血压偏高 PPG", "expected_uses": ["special_population"]},
    {"query": "老年人 65 岁 血压估算 复核", "expected_uses": ["special_population", "home_bp_monitoring"]},
    {"query": "家庭血压监测 上臂式 电子血压计", "expected_uses": ["home_bp_monitoring", "device_advice"]},
    {"query": "腕式 手指式 血压计 可靠吗 上臂式", "expected_uses": ["device_advice", "home_bp_monitoring"]},
    {"query": "经过验证的血压计 STRIDE BP", "expected_uses": ["validated_devices", "device_advice"]},
    {"query": "复测前休息五分钟 血压测量", "expected_uses": ["remeasurement", "home_bp_monitoring"]},
    {"query": "连续多天记录 家庭血压 趋势", "expected_uses": ["home_bp_monitoring", "remeasurement"]},
    {"query": "减少钠盐摄入 血压 生活方式", "expected_uses": ["lifestyle"]},
    {"query": "规律运动 控制血压 生活方式", "expected_uses": ["lifestyle"]},
    {"query": "体重管理 血压 健康建议", "expected_uses": ["lifestyle"]},
    {"query": "戒烟 限酒 睡眠 压力 血压", "expected_uses": ["lifestyle"]},
    {"query": "中国 高血压 指南 2024 中文场景", "expected_uses": ["bp_category_reference"]},
    {"query": "AHA 血压分类 normal elevated stage 2", "expected_uses": ["bp_category_reference"]},
    {"query": "NICE 家庭血压监测 动态血压", "expected_uses": ["home_bp_monitoring"]},
    {"query": "ESC 2024 血压 指南 家庭测量", "expected_uses": ["home_bp_monitoring", "bp_category_reference"]},
    {"query": "ISO 81060 血压计 验证 标准", "expected_uses": ["device_advice", "research_background"]},
    {"query": "报告 免责声明 PPG 不能替代诊断", "expected_uses": ["disclaimer", "cuffless_ppg_limitations"]},
]


def _evidence_matches(evidence, expected_uses: List[str]) -> bool:
    allowed = set(evidence.allowed_uses or [])
    expected = set(expected_uses)
    if "validated_devices" in expected and evidence.topic == "validated_devices":
        return True
    return bool(allowed & expected)


def evaluate_retrieval(top_k: int = 5) -> Dict:
    rows = []
    for case in GOLDEN_QUERIES:
        result = retrieve_knowledge([case["query"]], top_k=top_k)
        evidence = result.evidence
        matches = [item for item in evidence if _evidence_matches(item, case["expected_uses"])]
        precision = len(matches) / len(evidence) if evidence else 0.0
        sensitive = bool(case.get("sensitive"))
        unsafe = [
            item.source_id
            for item in evidence
            if sensitive and item.evidence_class not in HIGH_TRUST_EVIDENCE_CLASSES
        ]
        rows.append(
            {
                "query": case["query"],
                "expected_uses": case["expected_uses"],
                "retrieved": [item.model_dump() for item in evidence],
                "precision_at_k": round(precision, 3),
                "has_match": bool(matches),
                "unsafe_source_leakage": unsafe,
            }
        )

    summary = {
        "query_count": len(rows),
        "match_rate": round(sum(1 for row in rows if row["has_match"]) / len(rows), 3),
        "mean_precision_at_5": round(sum(row["precision_at_k"] for row in rows) / len(rows), 3),
        "unsafe_source_leakage_count": sum(len(row["unsafe_source_leakage"]) for row in rows),
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    result = evaluate_retrieval()
    out_path = resolve_project_path("knowledge_base/processed/retrieval_evaluation.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
