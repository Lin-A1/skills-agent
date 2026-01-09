---
name: websearch_service
description: |
  Use ONLY for retrieving **real-time information**, **specific facts**, **news**, **events**, and **unknown entities** (companies, products, people) that are NOT in your internal knowledge base.
  **Strictly** for external/dynamic information retrieval.
client_class: WebSearchClient
default_method: search
---

## 功能
通过 SearXNG 搜索引擎获取网页结果，使用 VLM 对网页内容进行智能分析和结构化提取。
具备双层缓存机制（向量语义缓存 + 数据库缓存）。

## 调用方式
```python
from services.websearch_service.client import WebSearchClient

client = WebSearchClient()

# 健康检查
status = client.health_check()

# 联网搜索（自动使用缓存）
result = client.search("Python async编程", max_results=5)

# 强制刷新（忽略缓存）
result = client.search("最新AI技术", max_results=3, force_refresh=True)
result2 = client.search("openai", max_results=3, force_refresh=True)

# 获取结果
for r in result["results"]:
    print(r["title"], r["data"]["main_content"])
    
for r in result2["results"]:
    print(r["title"], r["data"]["main_content"])
```

## 返回格式
```json
{
  "query": "Python async编程",
  "total": 3,
  "success_count": 3,
  "cached_count": 2,
  "results": [
    {
      "index": 1,
      "title": "Python异步编程",
      "url": "https://...",
      "source_domain": "example.com",
      "success": true,
      "from_cache": true,
      "data": {
        "title_summary": "Python异步编程概述",
        "main_content": "Python异步编程基于asyncio库...",
        "key_information": ["asyncio是标准库", "使用async/await语法"],
        "credibility": "authoritative",
        "relevance_score": 0.92
      }
    }
  ],
  "search_timestamp": "2025-12-28T18:30:00"
}
```
