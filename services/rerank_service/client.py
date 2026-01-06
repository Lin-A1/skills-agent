"""Rerank 服务客户端"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class RerankServiceClient:
    """Rerank 服务客户端类"""

    def __init__(self, base_url: str | None = None):
        """初始化客户端

        Args:
            base_url: 服务地址，如果为 None 则从环境变量读取
        """
        if base_url is None:
            host = os.getenv("RERANK_HOST", "localhost")
            port = os.getenv("RERANK_PORT", "8003")
            base_url = f"http://{host}:{port}"

        self.base_url = base_url.rstrip("/")
        self.model = os.getenv("RERANK_MODEL_NAME", "Qwen/Qwen3-Reranker-0.6B")

    def rerank(
            self,
            query: str,
            documents: list[str],
            top_n: int | None = None,
            return_documents: bool = True,
    ) -> dict:
        """对文档列表进行重排序

        Args:
            query: 查询文本
            documents: 文档列表
            top_n: 返回前 N 个结果，如果为 None 则返回所有结果
            return_documents: 是否在结果中返回文档文本

        Returns:
            包含重排序结果的字典
        """
        url = f"{self.base_url}/v1/rerank"
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "return_documents": return_documents,
        }

        if top_n is not None:
            payload["top_n"] = top_n

        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def rerank_documents(
            self, query: str, documents: list[str], top_n: int = 5
    ) -> list[tuple[int, float, str]]:
        """对文档重排序并返回简化结果（简化接口）

        Args:
            query: 查询文本
            documents: 文档列表
            top_n: 返回前 N 个结果

        Returns:
            (索引, 分数, 文档) 的元组列表，按分数降序排列
        """
        result = self.rerank(
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=True,
        )

        # 提取结果
        ranked_docs = []
        for item in result.get("results", []):
            index = item["index"]
            score = item["relevance_score"]
            doc = item.get("document", {}).get("text", "")
            ranked_docs.append((index, score, doc))

        return ranked_docs

    def get_top_indices(
            self, query: str, documents: list[str], top_n: int = 5
    ) -> list[int]:
        """获取最相关文档的索引（最简化接口）

        Args:
            query: 查询文本
            documents: 文档列表
            top_n: 返回前 N 个结果

        Returns:
            最相关文档的索引列表
        """
        result = self.rerank(
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=False,
        )

        return [item["index"] for item in result.get("results", [])]


if __name__ == "__main__":
    # 测试代码
    client = RerankServiceClient()

    # 测试数据
    query = "什么是机器学习？"
    documents = [
        "机器学习是人工智能的一个分支，通过数据训练模型。",
        "今天天气很好，适合出去散步。",
        "深度学习是机器学习的子领域，使用神经网络。",
        "Python 是一种流行的编程语言。",
        "监督学习需要标注数据来训练模型。",
    ]

    # 方式1：获取完整结果
    print("完整重排序结果:")
    result = client.rerank(query, documents, top_n=3)
    print(f"模型: {result.get('model')}")
    for item in result.get("results", []):
        print(f"  索引: {item['index']}, 分数: {item['relevance_score']:.4f}")

    # 方式2：获取简化结果
    print("\n简化结果（带文档内容）:")
    ranked = client.rerank_documents(query, documents, top_n=3)
    for idx, score, doc in ranked:
        print(f"  [{idx}] {score:.4f} - {doc[:30]}...")

    # 方式3：只获取索引
    print("\n只获取索引:")
    indices = client.get_top_indices(query, documents, top_n=3)
    print(f"  Top 3 索引: {indices}")
