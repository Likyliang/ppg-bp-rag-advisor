# 导师汇报用：embedding 检索展示

- 生成时间：2026-06-03 10:46
- 分支定位：从 3ad8763 拉出的演示分支，只展示检索侧预研，不接入最新报告优化分支。
- 展示边界：默认隐藏原文片段，只展示来源标题、主题、证据等级、用途标签和分数。

## 当前索引状态

- local_fulltext_hashing: local_hashing_vectors, 384维, 67个PDF来源, 2446页, 14849条全文分块
- openai_processed_chunks: text-embedding-3-small, 1536维, 629条分块, 136个来源, scope=processed_chunks
- openai_fulltext_chunks: text-embedding-3-small, 1536维, 1000条分块, 14个来源, scope=fulltext_chunks

## 查询演示

每个问题同时展示两类结果：

- 当前主链路：治理分块 + 关键词/用途标签/证据等级/质量分加权。
- 本地全文向量：384维哈希向量，刻意不叠加安全过滤，用于展示 embedding 类检索的形态和潜在缺陷。

### 手机PPG估算血压为什么不能替代上臂式血压计？

- 推断用途标签：`cuffless_ppg_limitations, device_advice`

**当前主链路结果**

| rank | score | title | topic | region/class | allowed_uses |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.6373 | Cuffless Devices for the Measurement of Blood Pressure | cuffless_ppg_limitations | AHA / scientific_statement | cuffless_ppg_limitations, device_advice, signal_quality, research_background |
| 2 | 0.6198 | Cuffless Devices for the Measurement of Blood Pressure | cuffless_ppg_limitations | AHA / scientific_statement | cuffless_ppg_limitations, device_advice, signal_quality, research_background |
| 3 | 0.6183 | Cuffless Devices for the Measurement of Blood Pressure | cuffless_ppg_limitations | AHA / scientific_statement | cuffless_ppg_limitations, device_advice, signal_quality, research_background |


**本地全文向量结果**

| rank | score | title | topic | page | region/class | allowed_uses |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.5471 | 中国血压测量指南 | home_bp_monitoring | 5 | guideline | home_bp_monitoring, remeasurement, device_advice |
| 2 | 0.5468 | 中国高血压患者教育指南 | lifestyle | 62 | patient_education | lifestyle, home_bp_monitoring, disclaimer |
| 3 | 0.5421 | 2019中国家庭血压监测指南 | home_bp_monitoring | 3 | guideline | home_bp_monitoring, remeasurement, device_advice, bp_category_reference |


### 低质量PPG信号下，用户应该如何复测和记录？

- 推断用途标签：`cuffless_ppg_limitations, remeasurement, signal_quality`

**当前主链路结果**

| rank | score | title | topic | region/class | allowed_uses |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.7522 | PPG signal quality and confidence safety rule | measurement_quality | global / safety_rule | signal_quality, remeasurement, cuffless_ppg_limitations |
| 2 | 0.7127 | Camera PPG capture environment rule | measurement_quality | global / safety_rule | signal_quality, remeasurement, cuffless_ppg_limitations |
| 3 | 0.696 | PPG ambient light feature interpretation rule | measurement_quality | global / safety_rule | signal_quality, remeasurement, cuffless_ppg_limitations, research_background |


**本地全文向量结果**

| rank | score | title | topic | page | region/class | allowed_uses |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.2482 | 国家基本公共卫生服务规范（第三版）高血压患者健康管理服务规范 | home_bp_monitoring | 90 | guideline | home_bp_monitoring, remeasurement, special_population, emergency_alert |
| 2 | 0.2372 | 2019中国家庭血压监测指南 | home_bp_monitoring | 3 | guideline | home_bp_monitoring, remeasurement, device_advice, bp_category_reference |
| 3 | 0.2348 | Cuffless Blood Pressure Monitoring Devices - Technical Foundations and Clinical  | cuffless_ppg_limitations | 12 | scientific_statement | cuffless_ppg_limitations, device_advice, research_background, disclaimer |


### 如果血压估算很高并伴有胸痛，报告应该优先提示什么？

- 推断用途标签：`emergency_alert`

**当前主链路结果**

| rank | score | title | topic | region/class | allowed_uses |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.6156 | Hypertensive crisis | emergency | US / official_health_education | emergency_alert |
| 2 | 0.6004 | Understanding Blood Pressure Readings | bp_categories | AHA / official_health_education | bp_category_reference, emergency_alert, remeasurement |
| 3 | 0.5904 | Hypertensive emergency safety rule | emergency | global / safety_rule | emergency_alert |


**本地全文向量结果**

| rank | score | title | topic | page | region/class | allowed_uses |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.4271 | 中国高血压患者教育指南 | lifestyle | 9 | patient_education | lifestyle, home_bp_monitoring, disclaimer |
| 2 | 0.3906 | 成人高血压食养指南（2023年版） | lifestyle | 56 | guideline | lifestyle, home_bp_monitoring, remeasurement, special_population |
| 3 | 0.3751 | 中国高血压患者教育指南 | lifestyle | 14 | patient_education | lifestyle, home_bp_monitoring, disclaimer |


### 连续几天家庭血压偏高，应该怎么记录并和医生沟通？

- 推断用途标签：`bp_category_reference, device_advice, home_bp_monitoring, remeasurement`

**当前主链路结果**

| rank | score | title | topic | region/class | allowed_uses |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.8417 | 2019中国家庭血压监测指南 | home_bp_monitoring | CN / guideline | home_bp_monitoring, remeasurement, device_advice, bp_category_reference |
| 2 | 0.8215 | Measurement of Blood Pressure in Humans - A Scientific Statement From the Americ | home_bp_monitoring | AHA / scientific_statement | home_bp_monitoring, remeasurement, device_advice, bp_category_reference |
| 3 | 0.8088 | 2019中国家庭血压监测指南 | home_bp_monitoring | CN / guideline | home_bp_monitoring, remeasurement, device_advice, bp_category_reference |


**本地全文向量结果**

| rank | score | title | topic | page | region/class | allowed_uses |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.4138 | 2019中国家庭血压监测指南 | home_bp_monitoring | 2 | guideline | home_bp_monitoring, remeasurement, device_advice, bp_category_reference |
| 2 | 0.3844 | 2019中国家庭血压监测指南 | home_bp_monitoring | 4 | guideline | home_bp_monitoring, remeasurement, device_advice, bp_category_reference |
| 3 | 0.3761 | 2019中国家庭血压监测指南 | home_bp_monitoring | 2 | guideline | home_bp_monitoring, remeasurement, device_advice, bp_category_reference |


## 汇报时可以主动暴露的缺陷

- 纯向量命中有时更像“语义相似”，不一定自动满足医疗安全场景需要。
- 对急症、用药、孕产妇等敏感问题，仍必须叠加用途标签、证据等级和高信任来源过滤。
- 本地哈希向量不等价于真正语义 embedding，适合做离线演示和检索调试，不适合作为最终结论。
- 急症问题可能被裸向量召回到生活方式或普通监测材料，这恰好可以说明安全过滤层仍然必要。
- OpenAI embedding 试验已有索引规模，但现场查询需要 API key；因此本演示优先使用可离线展示的本地向量。

## 汇报话术

> 这周我把 embedding 检索侧做了一个演示分支：当前主链路仍以可解释检索和安全元数据过滤为主，embedding 主要作为候选证据召回的预研方向。它对英文专业文献和同义表达可能有帮助，但在医疗安全场景里不能单独使用，后续要继续比较命中稳定性、引用覆盖和敏感场景的安全过滤。
