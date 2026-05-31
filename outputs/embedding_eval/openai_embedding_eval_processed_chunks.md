# OpenAI Embedding 检索评估

- scope: `processed_chunks`
- top_k: 5
- model: `text-embedding-3-small`
- query embedding tokens: 2051
- cn_boost: 0.03
- high_trust_boost: 0.02
- duration_sec: 3.3

| mode | match_rate | precision@5 | topic_hit | topic_precision@5 | class_hit | high_trust_sensitive | unsafe_leakage | top1_CN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_keyword_retriever | 1.0 | 1.0 | 1.0 | 0.908 | 1.0 | 1.0 | 0 | 0.13 |
| openai_embedding_metadata_augmented | 0.95 | 0.908 | 0.95 | 0.892 | 1.0 | 0.99 | 0 | 0.11 |
| openai_embedding_inferred_uses | 0.99 | 0.99 | 0.99 | 0.972 | 1.0 | 1.0 | 0 | 0.1 |
| openai_embedding_hybrid_cn_boost | 0.99 | 0.988 | 0.99 | 0.948 | 1.0 | 1.0 | 0 | 0.17 |
| openai_embedding_expected_uses | 1.0 | 1.0 | 1.0 | 0.972 | 1.0 | 1.0 | 0 | 0.1 |

## 解读口径

- `openai_embedding_metadata_augmented` 表示用标题、主题、allowed_uses 等治理元数据增强后的 embedding 检索，但不加 allowed_uses 过滤；它不是纯内容向量。
- `openai_embedding_inferred_uses` 表示用现有规则从 query 推断 allowed_uses 后再做 embedding 检索，更接近真实系统接入方式。
- `openai_embedding_hybrid_cn_boost` 在 inferred allowed_uses 基础上，给中国来源和高可信来源轻量加权，用来观察中文用户场景下的本土权威来源优先效果。
- `openai_embedding_expected_uses` 是带答案标签的上限实验，用来观察如果 allowed_uses 完全正确，embedding 排序本身能达到什么效果。
- `top1_CN` 只表示第一条结果是否为中国来源；它不是唯一指标，但能帮助观察中文用户场景是否优先命中本土权威资料。
