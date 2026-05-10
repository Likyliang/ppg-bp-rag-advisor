# 全文候选清单与机构访问流程

本流程用于“全文候选清单 + 机构访问下载 + 摘要入库”专项迭代。目标是补强知识库证据质量，同时避免把受版权保护的全文或任何账号凭证写入仓库。

## 文件约定

- `knowledge_base/sources/fulltext_candidates.yaml`：全文候选治理清单，记录优先级、访问方式、是否需要机构身份、是否可自动下载、摘要状态和允许用途。
- `knowledge_base/sources/downloads/`：本地 PDF 暂存目录，已被 Git 忽略，只保存合法下载的全文文件。
- `knowledge_base/sources/fulltext_summaries/`：可提交的中文摘要笔记，只包含 citation、访问记录、摘要要点和安全边界。
- `knowledge_base/processed/fulltext_candidate_report.json`：候选校验报告。
- `knowledge_base/processed/fulltext_download_queue.md`：机构/浏览器下载队列。
- `knowledge_base/processed/fulltext_download_manifest.json`：公开 PDF 下载记录。
- `knowledge_base/processed/fulltext_summary_manifest.json`：摘要生成记录。

## 安全边界

- 不保存机构账号、密码、cookie、token 或浏览器会话数据。
- 需要机构访问时，只通过用户当前浏览器会话下载。
- 下载后的 PDF 不提交到 Git；只提交摘要化中文笔记。
- 摘要只服务 PPG 估算解释、复测建议、设备局限、生活方式教育和安全提醒。
- 不把全文内容扩展为诊断、治疗、开药、停药或替代规范血压测量能力。

## 命令

```bash
.venv/bin/python scripts/prepare_fulltext_candidates.py
.venv/bin/python scripts/download_fulltext_candidates.py
.venv/bin/python scripts/create_fulltext_summaries.py
.venv/bin/python scripts/extract_source_notes.py --clean
.venv/bin/python scripts/ingest_kb.py
```

完整质量门禁会自动校验候选清单并重新生成可提交摘要：

```bash
.venv/bin/python scripts/run_quality_gate.py --strict-stop
```

## 机构下载步骤

1. 运行 `scripts/prepare_fulltext_candidates.py`，查看 `knowledge_base/processed/fulltext_download_queue.md`。
2. 对 `queued_institution` 或 `queued_browser` 项，在浏览器中打开 `landing_url` 或 `pdf_url`。
3. 如需要机构身份，由用户在浏览器页面中自行登录；系统不读取、不保存密码。
4. 将合法下载的 PDF 保存为队列中给出的 `save_as` 文件名。
5. 人工阅读全文后，将中文摘要写入对应候选的 `summary_notes`，并把 `include_in_summary` 改为 `true`、`summary_status` 改为 `ready`。
6. 运行 `scripts/create_fulltext_summaries.py` 和完整质量门禁。
