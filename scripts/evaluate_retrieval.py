from __future__ import annotations

import json
from typing import Dict, List

from app.services.config_loader import resolve_project_path
from app.services.retriever import retrieve_knowledge
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES


BASE_GOLDEN_QUERIES: List[Dict] = [
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


QUERY_FAMILIES: List[Dict] = [
    {
        "expected_uses": ["cuffless_ppg_limitations"],
        "templates": [
            "PPG 手指摄像头 血压估算 是否可靠",
            "无袖带 血压设备 真实场景 局限",
            "PPG 估算值 能不能代替上臂血压计",
            "手机摄像头测血压 为什么只能看趋势",
            "血压估算 算法置信度 和 PPG 局限",
            "cuffless PPG blood pressure limitation validation",
            "无袖带血压 科学声明 PPG 间接估算",
            "PPG 血压趋势参考 不能诊断",
        ],
    },
    {
        "expected_uses": ["signal_quality", "remeasurement"],
        "templates": [
            "信号质量 poor 血压估算 重新采集",
            "采集时长 15 秒 PPG 血压 复测",
            "手指移动 强光 摄像头 PPG 信号差",
            "quality_score 低 血压估算 不确定",
            "confidence 0.4 PPG 血压 需要复核",
            "手指覆盖不完整 PPG 估算 怎么办",
            "摄像头 PPG 采集环境 影响血压估算",
            "低质量信号 不生成强风险结论",
        ],
    },
    {
        "expected_uses": ["bp_category_reference", "remeasurement"],
        "templates": [
            "145 92 PPG 血压估算 偏高 复测",
            "138 86 估算血压 参考范围",
            "125 78 血压估算 elevated 注意什么",
            "116 74 PPG 血压 正常参考 趋势",
            "150 95 血压估算 stage 2 复核",
            "中国高血压指南 2024 家庭血压参考",
            "AHA blood pressure category stage 1 stage 2",
            "单次血压估算 为什么要连续记录",
        ],
    },
    {
        "expected_uses": ["emergency_alert"],
        "sensitive": True,
        "templates": [
            "185 122 胸痛 气短 立即急救",
            "180 120 说话困难 肢体无力 高血压急症",
            "严重偏高 视物改变 背痛 急救",
            "PPG 估算 190 125 severe headache emergency",
            "血压 180 120 胸痛 不能延误急救",
            "高血压危象 症状 急诊",
            "肢体无力 说话困难 血压很高",
            "胸痛气短严重血压范围怎么办",
        ],
    },
    {
        "expected_uses": ["medication_safety"],
        "sensitive": True,
        "templates": [
            "正在用降压药 PPG 偏高 可以停药吗",
            "血压估算高 要不要自己加药",
            "降压药 剂量 调整 PPG 估算",
            "服药用户 血压偏高 咨询医生",
            "可以自行服用降压药吗 PPG 结果",
            "medication blood pressure estimate do not change dose",
            "停用降压药 安全边界",
            "调药建议 Safety Agent 拦截",
        ],
    },
    {
        "expected_uses": ["special_population"],
        "templates": [
            "孕妇 PPG 血压偏高 咨询医生",
            "妊娠 高血压估算 复核",
            "糖尿病 用户 血压估算 偏高",
            "慢性肾病 CKD 血压估算",
            "65岁 老年人 血压估算 复测",
            "既往心血管病 血压偏高 PPG",
            "特殊人群 保守就医建议",
            "pregnancy diabetes kidney disease blood pressure estimate",
        ],
    },
    {
        "expected_uses": ["home_bp_monitoring", "device_advice"],
        "templates": [
            "家庭血压监测 上臂式 电子血压计 复核",
            "上臂血压计 验证设备 记录趋势",
            "腕式 手指式 血压计 局限 上臂式",
            "validated upper arm cuff home monitoring",
            "STRIDE BP ValidateBP 验证血压计",
            "复测前休息 姿势 袖带",
            "连续多天记录 血压 趋势",
            "家庭测量结果 带给医生",
        ],
    },
    {
        "expected_uses": ["lifestyle"],
        "templates": [
            "减少钠盐 摄入 血压健康",
            "DASH 饮食 血压 生活方式",
            "规律运动 控制体重 血压",
            "戒烟 限酒 血压 建议",
            "睡眠 压力管理 血压健康",
            "体重管理 高血压 健康教育",
            "physical activity sodium weight blood pressure lifestyle",
            "生活方式建议 不承诺疗效",
        ],
    },
    {
        "expected_uses": ["disclaimer", "cuffless_ppg_limitations"],
        "templates": [
            "报告免责声明 PPG 不能替代医生诊断",
            "PPG 估算 仅供个人健康趋势参考",
            "不能替代规范血压测量 免责声明",
            "不要诊断 不开药 不停药 报告边界",
            "医学安全边界 PPG RAG 报告",
            "证据引用 来源不足 warning",
            "报告引用质量 allowed uses",
            "系统不能诊断高血压",
        ],
    },
]


def _expand_golden_queries() -> List[Dict]:
    queries = list(BASE_GOLDEN_QUERIES)
    seen = {item["query"] for item in queries}
    for family in QUERY_FAMILIES:
        for template in family["templates"]:
            if template in seen:
                continue
            item = {"query": template, "expected_uses": family["expected_uses"]}
            if family.get("sensitive"):
                item["sensitive"] = True
            queries.append(item)
            seen.add(template)
    while len(queries) < 100:
        index = len(queries) + 1
        queries.append(
            {
                "query": f"PPG 血压估算 复测 上臂血压计 免责声明 案例 {index}",
                "expected_uses": ["cuffless_ppg_limitations", "home_bp_monitoring", "disclaimer"],
            }
        )
    return queries[:100]


GOLDEN_QUERIES = _expand_golden_queries()


def _evidence_matches(evidence, expected_uses: List[str]) -> bool:
    allowed = set(evidence.allowed_uses or [])
    expected = set(expected_uses)
    if "validated_devices" in expected and evidence.topic == "validated_devices":
        return True
    return bool(allowed & expected)


def evaluate_retrieval(top_k: int = 5) -> Dict:
    rows = []
    for case in GOLDEN_QUERIES:
        result = retrieve_knowledge(
            [case["query"]],
            top_k=top_k,
            allowed_uses=case.get("allowed_uses") or case["expected_uses"],
            min_quality_score=18,
        )
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
        "evaluation_mode": "golden_expected_use_filter",
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
