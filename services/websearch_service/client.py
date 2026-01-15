"""
Web搜索服务客户端
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


class WebSearchClient:
    """联网Web搜索服务客户端"""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 120.0):
        """
        初始化客户端

        Args:
            base_url: 服务地址，默认从环境变量读取
            timeout: 请求超时时间（秒）
        """
        if base_url is None:
            host = os.getenv("SEARCH_SERVICE_HOST", "127.0.0.1")
            port = os.getenv("SEARCH_SERVICE_PORT", "8004")
            base_url = f"http://{host}:{port}"

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(
        self, 
        query: str, 
        max_results: int = 5, 
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        执行搜索分析

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            force_refresh: 是否强制刷新（忽略缓存）

        Returns:
            dict: 搜索响应
        """
        url = f"{self.base_url}/search"
        payload = {
            "query": query,
            "max_results": max_results,
            "force_refresh": force_refresh
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
    client = WebSearchClient()
    
    # 健康检查
    print(client.health_check())

    t1 = time.time()

    # 搜索
    result = client.search("PP-OCRv5", max_results=3)
    print(time.time() - t1)
    for r in result.get('results', []):
        print(f"- {r.get('title')}")