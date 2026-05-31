## 本次结果摘要
本次手指摄像头 PPG 算法估算血压为 149.0/94.0 mmHg，因信号质量不足，本次不做范围解释。
本次输入信息：信号质量分 0.44；PPG 置信度 0.42；采集时长 12.0 秒；来源 camera_finger。
该结果来自 PPG 估算，仅供个人健康趋势参考，不能替代规范血压测量。

## 个性化触发因素
- 读数触发：估算值 149.0/94.0 mmHg 对应 `quality_rule`，所以进入“因信号质量不足，本次不做范围解释”解释。
- 质量触发：本次信号质量不足，不生成强风险结论。
- 质量提醒：信号质量分低于阈值，本次估算不适合做风险解释。；上游估算置信度偏低，应优先复测。；采集时长偏短，建议重新采集不少于 20 秒。
- 急症筛查：未填报胸痛、气短、肢体无力、视物改变、说话困难或严重头痛等急症相关症状。
- 年龄：52 岁。
- 未填报妊娠、糖尿病、慢性肾脏病、既往心血管病史或正在使用降压药等需额外保守处理的因素。
- 指南地区：选择 CN，因此检索加入国家卫健委、基层高血压、食养和中国血压管理相关证据。

## 质量与风险解释
本次信号质量不足，不生成强风险结论。
本次信号质量不足，建议重新采集并使用经过验证的上臂式电子血压计复核。

## 为什么给出这些建议
- 本次质量不足，所以报告不展开血压范围解释，重点变为重新采集和规范设备复核。

## 建议
### 复测与记录
- 安静休息至少 5 分钟后重新测量。
- 连续多天记录测量趋势，避免只看单次估算值。
- 重新采集时保持手指覆盖摄像头、身体静止，避免强光干扰。
### 设备复核
- 使用经过验证的上臂式电子血压计进行复核。

## 参考来源
- [local_capture_environment_rule_001] Camera PPG capture environment rule（project） · safety_rule
- [aha_home_bp_monitoring_public_001] Home Blood Pressure Monitoring（American Heart Association） · official_health_education: https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings/monitoring-your-blood-pressure-at-home
- [chinese_2011_bp_measurement_guideline_002] 中国血压测量指南（中国高血压联盟 / 国家心血管病中心） · guideline: https://www.nccd.org.cn/UploadFile/201504/20150416170041172172.pdf
- [local_ppg_signal_quality_rule_002] PPG signal quality and confidence safety rule（project） · safety_rule
- [aha_home_bp_monitoring_public_003] Home Blood Pressure Monitoring（American Heart Association） · official_health_education: https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings/monitoring-your-blood-pressure-at-home

## 引用质量
证据覆盖率：1.0
建议证据绑定率：1.0
敏感用途高可信来源：是

## 免责声明
本报告仅供个人健康趋势参考，不能替代医生诊断、治疗决策或规范血压测量。如有不适或多次复核仍异常，请咨询专业医务人员。