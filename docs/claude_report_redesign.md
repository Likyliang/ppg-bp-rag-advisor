# Claude 版报告重构（claude/rag-report-redesign）

本分支针对"样例报告千篇一律、缺乏专业性、正文没有文献引用"的问题做了一次
以 Claude 为出品方的报告层重构，目标是：**更专业、可引用、并且不再因为安全规则
误触发而被迫退回到同一份保守模板。**

## 一、问题定位（千篇一律的真正来源）

逐层排查后确认有三层原因，而不是单一 bug：

1. **默认走 `template_only`（provider=mock）**：在没有配置 LLM key 时，每份报告都是
   同一套按血压档位分桶的固定文案，桶内逐字相同。

2. **正文没有文献引用**：检索其实是工作的（`chunks.jsonl` 有 629 条、质量分 18–25），
   但旧版只在结尾用 `## 参考来源` 平铺一个无编号列表（`来源类型：guideline: https://...`），
   正文里没有 `[n]` 引用，也没有学术化著录格式，且每份报告 top 命中的几乎都是同几条指南，
   观感上更显"一样"。

3. **安全规则误触发 → 兜底**（用户的判断基本正确）：codex 分支把
   `不需要.*120 / 暂不需要.*120 / 不需要.*急诊 / 暂时不需要.*急诊 …` 这一批
   "120/急诊安抚语"加进了**常驻** `diagnostic_patterns`。可是在**非急症**报告里，
   "目前没有急症症状，暂时不需要立即拨打120（出现症状要立刻打）"本来就是正确表述。
   于是合规的 LLM 输出也会被判 high → `review_safety` 不通过 → workflow 退回
   `llm_rag_safety_fallback_template`，最终大家又都变回同一份模板。

## 二、本次改动

### 1. 引用引擎（新增 `app/services/citations.py`）
- 给检索证据按出现顺序编号 `[1..N]`，写入 `Evidence.citation_number`。
- 建立 `allowed_use -> 引用编号` 索引：某段建议只会引用**被授权用于该用途**的来源。
- `## 参考文献` 改为专业著录：`[n] 机构. 标题[类型]. 地区，年份. DOI/PMID/URL`。
- `Evidence` 模型新增 `year / doi / pmid / citation_number`，并在检索时从 chunk 回填。

### 2. 正文内联引用（`generator.py`）
- 在结论档位、各建议分组标题（复测/设备/生活方式/就医）、易误解点、急症提示等处
  按用途插入 `[n]` 标注；`## 参考来源` 统一改名为 `## 参考文献`。

### 3. 安全规则上下文化（`safety.py` + `config/safety_terms.yaml`）
- 把 120/急诊 安抚语从常驻 `diagnostic_patterns` 拆到新键
  `emergency_false_reassurance_patterns`，**只有在 `rule_result.emergency` 为真时**才判违规。
- 诊断断言、停药/改药、设备夸大、"不用复测/无需就医"等仍然是常驻硬红线，行为不变。
- 效果：非急症的专业表述不再被误杀，因而不再被迫兜底回模板；急症场景下"不需要120"
  这类危险安抚依然会被拦截。

### 4. Claude（Anthropic）出品通道（`llm_adapter.py` + `generator.py`）
- 新增 `generate_anthropic_report_body` / `generate_anthropic_input_only_report`，
  走 Anthropic Messages API；在同样的安全约束下重写正文，并按编号 `[n]` 内联引用证据
  （参考文献列表仍由系统统一附加，避免模型编造来源）。
- 通过 `LLM_PROVIDER=anthropic`（别名 `claude`）+ `REPORT_MODE=llm_rag` 启用，
  生成模式标记为 `llm_rag_anthropic:<model>`；失败时仍安全回退。

## 三、如何启用 Claude 出品的 RAG 报告

```bash
export LLM_PROVIDER=anthropic        # 或 claude
export REPORT_MODE=llm_rag
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-sonnet-4-5   # 可调
```

不配置 key 时系统仍可运行：默认 `template_only`，但现在模板正文也带 `[n]` 引用与
专业 `## 参考文献`，比旧版更专业、可追溯。

## 四、测试
新增 `tests/test_citations.py`（引用引擎），并在 `tests/test_safety.py`、
`tests/test_report_api.py` 增补：安全规则上下文化（非急症放行 / 急症拦截）、
正文内联引用与参考文献、Claude 通道接入（RAG 与非 RAG 对照）。
运行：`.venv/bin/python -m pytest -q`。
