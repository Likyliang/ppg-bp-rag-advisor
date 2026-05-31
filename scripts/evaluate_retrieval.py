from __future__ import annotations

import csv
import json
from typing import Dict, Iterable, List, Set

from app.services.config_loader import resolve_project_path
from app.services.retriever import retrieve_knowledge
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES


USE_TOPIC_MAP = {
    "bp_category_reference": ["bp_categories"],
    "cuffless_ppg_limitations": ["cuffless_ppg_limitations", "measurement_quality"],
    "device_advice": ["validated_devices", "home_bp_monitoring", "cuffless_ppg_limitations"],
    "disclaimer": ["disclaimer", "cuffless_ppg_limitations"],
    "emergency_alert": ["emergency"],
    "home_bp_monitoring": ["home_bp_monitoring", "measurement_quality"],
    "lifestyle": ["lifestyle"],
    "medication_safety": ["medication_safety"],
    "remeasurement": ["home_bp_monitoring", "measurement_quality"],
    "research_background": ["cuffless_ppg_limitations", "measurement_quality"],
    "signal_quality": ["measurement_quality", "cuffless_ppg_limitations"],
    "special_population": ["special_population"],
    "validated_devices": ["validated_devices"],
}

USE_EVIDENCE_CLASS_MAP = {
    "bp_category_reference": ["guideline", "official_health_education", "safety_rule"],
    "cuffless_ppg_limitations": ["scientific_statement", "guideline", "official_health_education", "review", "research_context", "safety_rule"],
    "device_advice": ["validation_standard", "official_registry", "guideline", "official_health_education"],
    "disclaimer": ["safety_rule", "scientific_statement", "official_health_education"],
    "emergency_alert": ["guideline", "official_health_education", "safety_rule"],
    "home_bp_monitoring": ["guideline", "official_health_education", "official_registry"],
    "lifestyle": ["guideline", "official_health_education"],
    "medication_safety": ["guideline", "official_health_education", "safety_rule"],
    "remeasurement": ["guideline", "official_health_education", "safety_rule"],
    "research_background": ["review", "research_context", "scientific_statement", "safety_rule"],
    "signal_quality": ["review", "research_context", "scientific_statement", "official_health_education", "safety_rule"],
    "special_population": ["guideline", "official_health_education"],
    "validated_devices": ["validation_standard", "official_registry", "guideline"],
}


BASE_GOLDEN_QUERIES: List[Dict] = [
    {"query": "PPG 血压估算准确吗 可以替代血压计吗", "expected_uses": ["cuffless_ppg_limitations"]},
    {"query": "无袖带 血压 设备 局限 PPG", "expected_uses": ["cuffless_ppg_limitations"]},
    {"query": "手指摄像头 PPG 信号质量差 怎么办", "expected_uses": ["signal_quality", "remeasurement"]},
    {"query": "置信度低 血压估算 是否可信", "expected_uses": ["signal_quality", "cuffless_ppg_limitations"]},
    {"query": "PPG 运动伪影 手指移动 光学信号质量", "expected_uses": ["signal_quality", "remeasurement"]},
    {"query": "PPG 接触压力 过紧 过松 波形质量", "expected_uses": ["signal_quality"]},
    {"query": "摄像头 PPG 肤色 环境光 影响 测量", "expected_uses": ["signal_quality", "research_background"]},
    {"query": "PPG 采集时长 采样 信号处理 最佳实践", "expected_uses": ["signal_quality", "research_background"]},
    {"query": "motion_artifact_score 偏高 PPG 手指移动 重新采集", "expected_uses": ["signal_quality", "remeasurement"]},
    {"query": "finger_coverage_score 低 手指覆盖不完整 摄像头 PPG", "expected_uses": ["signal_quality", "remeasurement"]},
    {"query": "contact_pressure_level high 手指按压过紧 PPG 波形质量", "expected_uses": ["signal_quality"]},
    {"query": "ambient_light_level bright 强光 摄像头 PPG 信号质量", "expected_uses": ["signal_quality", "research_background"]},
    {"query": "PPG 采集 8 秒 有效脉搏不足 能不能看", "expected_uses": ["signal_quality", "remeasurement"]},
    {"query": "PAT PTT 校准限制 可以证明血压准确吗", "expected_uses": ["cuffless_ppg_limitations", "research_background"]},
    {"query": "腕部 PPG 传感器位置 姿势 高度 信号质量", "expected_uses": ["signal_quality", "research_background"]},
    {"query": "可穿戴光学传感器 活动状态 运动 误差 PPG", "expected_uses": ["signal_quality", "research_background"]},
    {"query": "imaging PPG quality assessment ambient illumination motion artifact", "expected_uses": ["signal_quality", "research_background"]},
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
    {"query": "FDA 无袖带 血压设备 临床性能 测试 PPG", "expected_uses": ["cuffless_ppg_limitations", "device_advice"]},
    {"query": "WHO 袖带式 自动血压计 技术规范 验证设备", "expected_uses": ["device_advice", "home_bp_monitoring"]},
    {"query": "USPSTF 高血压筛查 诊室外 血压确认 家庭监测", "expected_uses": ["home_bp_monitoring", "remeasurement"]},
    {"query": "国家卫健委 高血压 营养 运动 指导原则 减盐", "expected_uses": ["lifestyle"]},
    {"query": "全国高血压日 规范测量 记录 生活方式", "expected_uses": ["home_bp_monitoring", "lifestyle"]},
    {"query": "KDIGO 2024 慢性肾病 CKD 血压偏高 复核", "expected_uses": ["special_population", "medication_safety"]},
    {"query": "ADA 2026 糖尿病 血压 心血管风险 用药安全", "expected_uses": ["special_population", "medication_safety"]},
    {"query": "国家基层高血压防治管理标准 2025 基层 随访 健康教育", "expected_uses": ["home_bp_monitoring", "special_population"]},
    {"query": "中国血压测量指南 测量姿势 复测 记录", "expected_uses": ["home_bp_monitoring", "remeasurement"]},
    {"query": "老年高血压 PPG 偏高 体位性低血压 咨询医生", "expected_uses": ["special_population", "remeasurement"]},
    {"query": "WHO 高血压药物治疗 PPG 结果 可以自行调药吗", "expected_uses": ["medication_safety"], "sensitive": True},
    {"query": "孕期 血压 160 110 头痛 视力改变 急救", "expected_uses": ["special_population", "emergency_alert"], "sensitive": True},
    {"query": "DASH 饮食 NHLBI 减盐 血压 生活方式", "expected_uses": ["lifestyle"]},
    {"query": "AHA 家庭血压测量 读两次 间隔一分钟 记录", "expected_uses": ["home_bp_monitoring", "remeasurement"]},
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


def _dedupe(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def _expected_topics(expected_uses: Iterable[str]) -> List[str]:
    topics: List[str] = []
    for use in expected_uses:
        topics.extend(USE_TOPIC_MAP.get(use, []))
    return _dedupe(topics)


def _expected_evidence_classes(expected_uses: Iterable[str]) -> List[str]:
    classes: List[str] = []
    for use in expected_uses:
        classes.extend(USE_EVIDENCE_CLASS_MAP.get(use, []))
    return _dedupe(classes)


def _normalize_case(item: Dict) -> Dict:
    expected_uses = _dedupe(item.get("expected_uses", []))
    normalized = {
        **item,
        "expected_uses": expected_uses,
        "expected_topics": item.get("expected_topics") or _expected_topics(expected_uses),
        "expected_evidence_classes": item.get("expected_evidence_classes") or _expected_evidence_classes(expected_uses),
        "scenario_type": item.get("scenario_type") or ("sensitive" if item.get("sensitive") else "general"),
    }
    return normalized


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
    return [_normalize_case(item) for item in queries[:100]]


GOLDEN_QUERIES = _expand_golden_queries()


def _evidence_matches(evidence, expected_uses: List[str]) -> bool:
    allowed = set(evidence.allowed_uses or [])
    expected = set(expected_uses)
    if "validated_devices" in expected and evidence.topic == "validated_devices":
        return True
    return bool(allowed & expected)


def _topic_matches(evidence, expected_topics: List[str]) -> bool:
    return bool(evidence.topic and evidence.topic in set(expected_topics))


def _class_matches(evidence, expected_classes: List[str]) -> bool:
    return bool(evidence.evidence_class and evidence.evidence_class in set(expected_classes))


def _unsafe_sources(evidence, sensitive: bool) -> List[str]:
    if not sensitive:
        return []
    unsafe = []
    for item in evidence:
        allowed = set(item.allowed_uses or [])
        if allowed & {"emergency_alert", "medication_safety", "special_population"}:
            if item.evidence_class not in HIGH_TRUST_EVIDENCE_CLASSES:
                unsafe.append(item.source_id)
    return unsafe


def _evaluate_mode(mode: str, top_k: int = 5) -> Dict:
    rows = []
    for case in GOLDEN_QUERIES:
        allowed_uses = None
        if mode == "metadata_filter_safety":
            allowed_uses = case.get("allowed_uses") or case["expected_uses"]
        result = retrieve_knowledge(
            [case["query"]],
            top_k=top_k,
            allowed_uses=allowed_uses,
            min_quality_score=18,
        )
        evidence = result.evidence
        matches = [item for item in evidence if _evidence_matches(item, case["expected_uses"])]
        topic_matches = [item for item in evidence if _topic_matches(item, case["expected_topics"])]
        class_matches = [item for item in evidence if _class_matches(item, case["expected_evidence_classes"])]
        precision = len(matches) / len(evidence) if evidence else 0.0
        topic_precision = len(topic_matches) / len(evidence) if evidence else 0.0
        sensitive = bool(case.get("sensitive"))
        unsafe = _unsafe_sources(evidence, sensitive)
        high_trust_sensitive = True
        if sensitive:
            sensitive_matches = [
                item for item in evidence
                if set(item.allowed_uses or []) & {"emergency_alert", "medication_safety", "special_population"}
            ]
            high_trust_sensitive = bool(sensitive_matches) and all(
                item.evidence_class in HIGH_TRUST_EVIDENCE_CLASSES for item in sensitive_matches
            )
        rows.append(
            {
                "mode": mode,
                "query": case["query"],
                "scenario_type": case.get("scenario_type", "general"),
                "expected_uses": case["expected_uses"],
                "expected_topics": case["expected_topics"],
                "expected_evidence_classes": case["expected_evidence_classes"],
                "retrieved": [item.model_dump() for item in evidence],
                "precision_at_k": round(precision, 3),
                "topic_precision_at_k": round(topic_precision, 3),
                "has_match": bool(matches),
                "has_topic_match": bool(topic_matches),
                "has_expected_class": bool(class_matches),
                "high_trust_sensitive": high_trust_sensitive,
                "unsafe_source_leakage": unsafe,
                "warnings": result.warnings,
            }
        )

    summary = {
        "query_count": len(rows),
        "match_rate": round(sum(1 for row in rows if row["has_match"]) / len(rows), 3),
        "mean_precision_at_5": round(sum(row["precision_at_k"] for row in rows) / len(rows), 3),
        "topic_hit_rate": round(sum(1 for row in rows if row["has_topic_match"]) / len(rows), 3),
        "mean_topic_precision_at_5": round(sum(row["topic_precision_at_k"] for row in rows) / len(rows), 3),
        "expected_class_hit_rate": round(sum(1 for row in rows if row["has_expected_class"]) / len(rows), 3),
        "high_trust_sensitive_rate": round(
            sum(1 for row in rows if row["scenario_type"] != "sensitive" or row["high_trust_sensitive"]) / len(rows),
            3,
        ),
        "unsafe_source_leakage_count": sum(len(row["unsafe_source_leakage"]) for row in rows),
        "evaluation_mode": mode,
    }
    return {"summary": summary, "rows": rows}


def evaluate_retrieval(top_k: int = 5) -> Dict:
    calibrated = _evaluate_mode("calibrated_query_only", top_k=top_k)
    metadata_filter = _evaluate_mode("metadata_filter_safety", top_k=top_k)
    return {
        "summary": calibrated["summary"],
        "rows": calibrated["rows"],
        "modes": {
            "calibrated_query_only": calibrated,
            "metadata_filter_safety": metadata_filter,
        },
    }


def main() -> None:
    result = evaluate_retrieval()
    out_path = resolve_project_path("knowledge_base/processed/retrieval_evaluation.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = resolve_project_path("knowledge_base/processed/retrieval_evaluation.csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        rows = result["modes"]["calibrated_query_only"]["rows"] + result["modes"]["metadata_filter_safety"]["rows"]
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "mode",
                "query",
                "scenario_type",
                "expected_uses",
                "expected_topics",
                "expected_evidence_classes",
                "precision_at_k",
                "topic_precision_at_k",
                "has_match",
                "has_topic_match",
                "has_expected_class",
                "high_trust_sensitive",
                "unsafe_source_leakage",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "mode": row["mode"],
                    "query": row["query"],
                    "scenario_type": row["scenario_type"],
                    "expected_uses": "|".join(row["expected_uses"]),
                    "expected_topics": "|".join(row["expected_topics"]),
                    "expected_evidence_classes": "|".join(row["expected_evidence_classes"]),
                    "precision_at_k": row["precision_at_k"],
                    "topic_precision_at_k": row["topic_precision_at_k"],
                    "has_match": row["has_match"],
                    "has_topic_match": row["has_topic_match"],
                    "has_expected_class": row["has_expected_class"],
                    "high_trust_sensitive": row["high_trust_sensitive"],
                    "unsafe_source_leakage": "|".join(row["unsafe_source_leakage"]),
                }
            )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(json.dumps({"metadata_filter_safety": result["modes"]["metadata_filter_safety"]["summary"]}, ensure_ascii=False, indent=2))
    print(f"wrote {out_path}")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
