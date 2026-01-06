"""RAG 服务客户端"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class RAGServiceClient:
    """RAG 服务客户端类"""

    def __init__(self, base_url: str | None = None):
        """初始化客户端

        Args:
            base_url: 服务地址，如果为 None 则从环境变量读取
        """
        if base_url is None:
            host = os.getenv("RAG_HOST", "localhost")
            port = os.getenv("RAG_SERVICE_PORT", "8008")
            base_url = f"http://{host}:{port}"

        self.base_url = base_url.rstrip("/")
        self.timeout = 30

    def retrieve(
        self,
        query: str,
        collection_name: str = "websearch_results",
        top_k: int = 5,
        min_score: float = 0.7,
        rerank: bool = True
    ) -> Dict[str, Any]:
        """
        语义检索

        Args:
            query: 查询文本
            collection_name: 集合名称
            top_k: 返回结果数量
            min_score: 最小相似度阈值
            rerank: 是否进行重排序

        Returns:
            检索结果
        """
        url = f"{self.base_url}/retrieve"
        payload = {
            "query": query,
            "collection_name": collection_name,
            "top_k": top_k,
            "min_score": min_score,
            "rerank": rerank
        }

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def retrieve_texts(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.7
    ) -> List[str]:
        """
        检索并返回文本列表

        Args:
            query: 查询文本
            top_k: 返回结果数量
            min_score: 最小相似度阈值

        Returns:
            文本列表
        """
        result = self.retrieve(query, top_k=top_k, min_score=min_score)
        return [r["text"] for r in result.get("results", [])]

    def save(
        self,
        documents: List[Dict[str, Any]],
        collection_name: str = "websearch_results"
    ) -> Dict[str, Any]:
        """
        保存文档到向量数据库

        Args:
            documents: 文档列表，每个文档包含 text 和 metadata
            collection_name: 集合名称

        Returns:
            保存结果
        """
        url = f"{self.base_url}/save"
        payload = {
            "collection_name": collection_name,
            "documents": documents
        }

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def health(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态
        """
        url = f"{self.base_url}/health"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    # 测试代码
    client = RAGServiceClient()

    # 健康检查
    print("健康检查:")
    print(client.health())

    # 测试检索
    print("\n测试检索:")
    result = client.retrieve("mimo-v2-flash", top_k=3)
    print(f"找到 {result['total']} 条结果")
    for r in result["results"]:
        print(f"  - {r['text'][:50]}... (score: {r['score']:.2f})")
