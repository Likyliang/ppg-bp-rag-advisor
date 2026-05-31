# Chunk 分割过程演示稿

目标：组会现场用 2-3 分钟讲清楚 PDF 如何从“全文文件”变成“可检索、可追溯、带安全边界的 chunks”。

## 1. 处理链路

```mermaid
flowchart LR
  A[公开/合规 PDF] --> B[来源治理: source_id, allowed_uses, access_note]
  B --> C[pypdf 按页抽取文本]
  C --> D[文本清洗: 去空字符, 合并空白, 保留段落边界]
  D --> E[句子/段落切分]
  E --> F[约 850 字符窗口 + 140 字符重叠]
  F --> G[写入 chunk metadata: 页码, sha256, 来源, 用途]
  G --> H[本地 hashing vector 索引]
  H --> I[RAG 检索候选证据]
```

## 2. 分割规则

- 抽取单位：PDF page。每个 chunk 都保留 `page_start/page_end`，方便回溯。
- 切分边界：优先按句末、中文/英文标点、段落空行切分。
- 目标长度：约 `850` 字符。
- 重叠长度：相邻 chunk 保留约 `140` 字符上下文，降低断句导致的语义丢失。
- 元数据：`source_id`、标题、机构、主题、证据等级、allowed_uses、PDF sha256、页码和治理说明。
- 向量：本地 deterministic hashing vector，维度 384；不依赖外部 embedding API，便于 demo 和审计。

## 3. 人造短例说明重叠窗口

假设目标长度是 30 字、重叠 8 字：

```text
原文：家庭血压监测需要使用经过验证的上臂式袖带设备。PPG 小程序结果只能作为趋势参考，不能替代规范血压测量。
chunk_01: 家庭血压监测需要使用经过验证的上臂式袖带设备。
chunk_02: 上臂式袖带设备。PPG 小程序结果只能作为趋势参考，不能替代规范血压测量。
重叠片段: 上臂式袖带设备。
```

这个重叠不是为了增加证据数量，而是为了让检索时跨句语义不会被硬切断。

## 4. 真实库中的 chunk 元数据示例（不展示 PDF 原文）

| 顺序 | chunk_id | source_id | 页码 | 字符数 | 与前一块是否有 140 字上下文重叠 |
|---:|---|---|---:|---:|---|
| 1 | `fulltext::aha_cuffless_bp_scientific_statement::p007::c01` | `aha_cuffless_bp_scientific_statement` | 7 | 410 | - |
| 2 | `fulltext::aha_cuffless_bp_scientific_statement::p007::c02` | `aha_cuffless_bp_scientific_statement` | 7 | 789 | 是 |
| 3 | `fulltext::aha_cuffless_bp_scientific_statement::p007::c03` | `aha_cuffless_bp_scientific_statement` | 7 | 766 | 是 |
| 4 | `fulltext::aha_cuffless_bp_scientific_statement::p007::c04` | `aha_cuffless_bp_scientific_statement` | 7 | 813 | 是 |

## 5. 现场讲法

可以这样讲：我们没有把 PDF 全文提交到仓库，而是在本地把可合法使用的 PDF 按页抽取、按句子边界切成小块，并为每个 chunk 绑定来源、页码、sha256 和允许用途。正式报告引用的是治理后的摘要 KB；本地全文向量主要用于 demo 检索和定位证据，不作为临床判断依据。

