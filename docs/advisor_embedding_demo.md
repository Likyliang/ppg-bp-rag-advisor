# 导师汇报用 embedding 检索展示分支

本分支用于组会或导师沟通时展示“检索侧 embedding 预研”的使用方式。它从 `3ad8763` 拉出，不接入后续更激进的报告质量返修提交，因此适合保留一点可讨论空间。

## 讲述定位

可以把这部分放在文献库和报告质量之后，作为补充进展：

> 当前报告主链路仍然以可解释检索、用途标签过滤、证据等级和质量分为主。embedding 这周主要做了一个展示分支，用于观察向量召回在英文专业文献、PPG/无袖带相关问题上的表现。它目前还不是稳定结论，后续需要继续评估命中稳定性、引用覆盖和敏感场景的安全过滤。

## 演示命令

默认生成一份不含原文片段的 Markdown 展示稿：

```bash
python scripts/demo_embedding_retrieval_for_advisor.py \
  --output outputs/advisor_embedding_demo/embedding_retrieval_demo.md
```

如果只是本地给自己看，可以临时加短片段，但不要提交这类输出：

```bash
python scripts/demo_embedding_retrieval_for_advisor.py --show-snippets
```

## 展示内容

脚本会展示三层信息：

1. 当前索引规模：本地全文哈希向量、OpenAI embedding 试验索引的 manifest 数据。
2. 当前主链路结果：治理后的知识分块 + 关键词/用途标签/证据等级/质量分加权。
3. 本地全文向量结果：384维本地哈希向量检索，刻意不叠加安全过滤，展示 embedding 类召回的样子和潜在缺陷。

## 可以主动暴露的缺陷

- 纯向量召回可能只解决“语义相似”，不能自动保证医疗安全边界。
- 急症、用药、孕产妇等敏感场景仍然必须依赖用途标签、证据等级和高信任来源过滤。
- 本地哈希向量只是离线展示和调试方案，不等价于真正的语义 embedding。
- 急症问题可能被裸向量召回到生活方式或普通监测材料，这恰好可以说明安全过滤层仍然必要。
- OpenAI embedding 已有试验索引，但现场查询依赖 API key，因此不适合作为稳定汇报结论。

## 分支边界

- 不修改 `config/settings.yaml`。
- 不替换当前报告生成主链路。
- 不提交 `knowledge_base/vector_store/` 中的向量文件。
- 不提交 PDF 原文或全文 chunk 内容。
