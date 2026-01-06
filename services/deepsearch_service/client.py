"""
DeepSearch 服务客户端
"""
import os
import time
from typing import Optional, Dict, Any
from pathlib import Path

import requests
from dotenv import load_dotenv

# 加载 .env
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class DeepSearchClient:
    """深度搜索服务客户端"""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 180.0):
        """
        初始化客户端

        Args:
            base_url: 服务地址，默认从环境变量读取
            timeout: 请求超时时间（秒），深度搜索需要更长时间
        """
        if base_url is None:
            host = os.getenv("DEEPSEARCH_SERVICE_HOST", "127.0.0.1")
            port = os.getenv("DEEPSEARCH_SERVICE_PORT", "8007")
            base_url = f"http://{host}:{port}"

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(
        self, 
        query: str, 
        max_iterations: int = 3,
        queries_per_iteration: int = 3,
        depth_level: str = "normal"
    ) -> Dict[str, Any]:
        """
        执行深度搜索

        Args:
            query: 用户问题
            max_iterations: 最大迭代次数 (1-5)
            queries_per_iteration: 每轮查询数 (1-5)
            depth_level: 搜索深度 (quick/normal/deep)

        Returns:
            dict: 深度搜索响应，包含 report, sources, iterations
        """
        url = f"{self.base_url}/deepsearch"
        payload = {
            "query": query,
            "max_iterations": max_iterations,
            "queries_per_iteration": queries_per_iteration,
            "depth_level": depth_level
        }
        
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        url = f"{self.base_url}/health"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    # 使用示例
    client = DeepSearchClient()
    
    # 健康检查
    print("健康检查:", client.health_check())

    t1 = time.time()

    # 深度搜索
    result = client.search("deepseek-ocr是什么模型，谁开源的", max_iterations=2)
    
    print(f"\n耗时: {time.time() - t1:.2f}s")
    print(f"总迭代次数: {result.get('total_iterations')}")
    print(f"\n=== 综合报告 ===\n{result.get('report', '')[:500]}...")
    print(f"\n=== 来源 ({len(result.get('sources', []))}) ===")
    for s in result.get('sources', []):
        print(f"- {s.get('title')}: {s.get('url')}")
