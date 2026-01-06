"""Embedding 服务客户端"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class EmbeddingServiceClient:
    """Embedding 服务客户端类"""

    def __init__(self, base_url: str | None = None):
        """初始化客户端

        Args:
            base_url: 服务地址，如果为 None 则从环境变量读取
        """
        if base_url is None:
            host = os.getenv("EMBEDDING_HOST", "localhost")
            port = os.getenv("EMBEDDING_PORT", "8002")
            base_url = f"http://{host}:{port}"

        self.base_url = base_url.rstrip("/")
        self.model = os.getenv("EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")

    def embed(
        self, texts: list[str] | str, encoding_format: str = "float"
    ) -> dict:
        """生成文本的向量表示

        Args:
            texts: 单个文本或文本列表
            encoding_format: 编码格式，支持 'float' 或 'base64'

        Returns:
            包含向量数据的字典
        """
        if isinstance(texts, str):
            texts = [texts]

        url = f"{self.base_url}/v1/embeddings"
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": encoding_format,
        }

        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def embed_query(self, text: str) -> list[float]:
        """为单个查询文本生成向量

        Args:
            text: 查询文本

        Returns:
            向量列表
        """
        result = self.embed(text)
        return result["data"][0]["embedding"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """为多个文档生成向量

        Args:
            texts: 文档文本列表

        Returns:
            向量列表的列表
        """
        result = self.embed(texts)
        return [item["embedding"] for item in result["data"]]


if __name__ == "__main__":
    # 测试代码
    client = EmbeddingServiceClient()

    # 测试单个文本
    print("测试单个文本:")
    vector = client.embed_query("你好，世界")
    print(f"向量维度: {len(vector)}")
    print(f"前5个值: {vector[:5]}")

    # 测试多个文本
    print("\n测试多个文本:")
    texts = ["人工智能", "机器学习", "深度学习"]
    vectors = client.embed_documents(texts)
    print(f"生成了 {len(vectors)} 个向量")
    print(f"每个向量维度: {len(vectors[0])}")