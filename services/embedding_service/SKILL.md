---
name: embedding_service
description: 文本向量化服务，将文本转换为高维向量，用于语义相似度计算、聚类分析等
client_class: EmbeddingServiceClient
default_method: embed_query
---

## 功能
将输入文本转换为高维向量表示，用于语义相似度计算、聚类分析等下游任务。

## 调用方式
```python
from services.embedding_service.client import EmbeddingServiceClient

client = EmbeddingServiceClient()

# 单个文本向量化
vector = client.embed_query("人工智能")  # -> list[float]

# 多个文本向量化
texts = ["机器学习", "深度学习", "自然语言处理"]
vectors = client.embed_documents(texts)  # -> list[list[float]]
```

## 返回格式
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [-0.031, -0.016, -0.007, ...]
    }
  ],
  "model": "Qwen/Qwen3-Embedding-0.6B"
}
```
