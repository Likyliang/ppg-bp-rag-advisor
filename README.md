# PPG 血压估算结果 RAG-Agent

面向上游 PPG 小程序结构化输出的医学知识增强解释系统。项目不训练或验证 PPG 血压估计算法，只对估算结果做保守、可追溯、带安全边界的健康趋势解释。

## 功能

- 接收小程序估算 SBP/DBP、心率、信号质量、置信度、用户基础信息和症状。
- 字段别名归一化，支持 `SBP`、`DBP`、`HR`、`quality` 等输入。
- 规则引擎先行判断信号质量、估算血压参考范围、急症规则和特殊人群。
- RAG 检索经过筛选的知识库证据，空知识库时自动回退模板报告。
- Source catalog 记录来源、证据等级、筛选分、允许用途、版权/访问说明和审计状态。
- Safety Agent 拦截确诊、调药、停药、设备过度承诺和急症漏报。
- 提供 FastAPI、Streamlit Demo、知识库筛选/ingest/审计、检索评估和论文评估脚本。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
python scripts/screen_sources.py
python scripts/extract_source_notes.py --clean
python scripts/ingest_kb.py
python scripts/audit_kb.py
python scripts/evaluate_retrieval.py
pytest
uvicorn app.main:app --reload
streamlit run streamlit_app.py
```

可选向量索引：

```bash
python -m pip install -e ".[rag]"
python scripts/ingest_kb.py --vector
```

默认检索会读取 `knowledge_base/processed/chunks.jsonl` 并使用关键词 fallback，因此无需下载 embedding 模型也能运行。

## API

- `GET /api/v1/health`
- `POST /api/v1/reports/preview-rules`
- `POST /api/v1/reports/generate`
- `POST /api/v1/kb/ingest`
- `GET /api/v1/kb/sources`
- `GET /api/v1/kb/audit`
- `POST /api/v1/kb/search`

示例：

```json
{
  "estimated_sbp": 145,
  "estimated_dbp": 92,
  "heart_rate": 82,
  "signal_quality_score": 0.86,
  "confidence": 0.68,
  "age": 45,
  "symptoms": {
    "chest_pain": false,
    "shortness_of_breath": false
  }
}
```

## 医疗安全边界

报告必须明确：PPG 估算结果仅供个人健康趋势参考，不能替代医生诊断、治疗决策或规范血压测量。系统不得提供处方、停药、调药建议，也不得宣称 PPG 估算可替代规范血压计。

## 知识来源

知识库由 `knowledge_base/sources/source_catalog.yaml` 驱动。每个来源记录 evidence class、allowed uses、筛选分、版权/访问说明和访问日期；筛选通过后由 `scripts/extract_source_notes.py` 生成结构化 Markdown，再由 `scripts/ingest_kb.py` 写入 `chunks.jsonl`。

当前纳入来源覆盖 AHA/ACC 2025 高血压指南要点、AHA 家庭血压监测和血压读数解释、AHA 无袖带血压科学声明、中国高血压防治指南 2024 修订版、NICE/ESC/ISH/ESH 国际指南、CDC/WHO/NHLBI/MedlinePlus 公众健康教育、STRIDE BP 验证设备注册表，以及项目本地安全规则。

排除规则包括设备厂商营销页、新闻软文、声称无需复测的博客，以及单篇模型性能论文作为患者建议依据。此类来源只可作为 excluded source 或研究背景，不进入用户报告核心证据。
