"""
Agent Service Client
提供便捷的 Agent 服务调用接口
"""
import os
import json
from typing import Optional, Dict, Any, Generator, List
from pathlib import Path

import requests
from dotenv import load_dotenv

# 加载 .env
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class AgentClient:
    """Agent 服务客户端"""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 300.0):
        """
        初始化客户端

        Args:
            base_url: 服务地址，默认从环境变量读取
            timeout: 请求超时时间（秒）
        """
        if base_url is None:
            host = os.getenv("AGENT_SERVICE_HOST", "127.0.0.1")
            port = os.getenv("AGENT_SERVICE_PORT", "8009")
            base_url = f"http://{host}:{port}"

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ==================== Sessions ====================

    def create_session(
        self,
        title: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """创建会话"""
        url = f"{self.base_url}/api/agent/sessions"
        payload = {}
        if title:
            payload["title"] = title
        if model:
            payload["model"] = model
        if system_prompt:
            payload["system_prompt"] = system_prompt
        if temperature is not None:
            payload["temperature"] = temperature

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """获取会话"""
        url = f"{self.base_url}/api/agent/sessions/{session_id}"
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def list_sessions(
        self,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """列出会话"""
        url = f"{self.base_url}/api/agent/sessions"
        params = {"page": page, "page_size": page_size}
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        """删除会话"""
        url = f"{self.base_url}/api/agent/sessions/{session_id}"
        response = requests.delete(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ==================== Messages ====================

    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取会话消息"""
        url = f"{self.base_url}/api/agent/sessions/{session_id}/messages"
        params = {}
        if limit:
            params["limit"] = limit
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ==================== Agent Completion ====================

    def complete(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        非流式 Agent 完成

        Args:
            message: 用户消息
            session_id: 会话ID（可选）
            model: 模型名称
            temperature: 温度
            stream: 是否流式（此方法固定为 False）

        Returns:
            Agent 响应
        """
        url = f"{self.base_url}/api/agent/completions"
        payload = {
            "message": message,
            "stream": False
        }
        if session_id:
            payload["session_id"] = session_id
        if model:
            payload["model"] = model
        if temperature is not None:
            payload["temperature"] = temperature

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def stream_complete(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式 Agent 完成

        Args:
            message: 用户消息
            session_id: 会话ID（可选）
            model: 模型名称
            temperature: 温度

        Yields:
            Agent 事件字典
        """
        url = f"{self.base_url}/api/agent/completions"
        payload = {
            "message": message,
            "stream": True
        }
        if session_id:
            payload["session_id"] = session_id
        if model:
            payload["model"] = model
        if temperature is not None:
            payload["temperature"] = temperature

        response = requests.post(url, json=payload, stream=True, timeout=self.timeout)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                data = line.decode('utf-8')
                if data.startswith("data: "):
                    event_data = data[6:]
                    if event_data != "[DONE]":
                        try:
                            yield json.loads(event_data)
                        except json.JSONDecodeError:
                            pass

    # ==================== Skills ====================

    def list_skills(self) -> Dict[str, Any]:
        """列出所有技能"""
        url = f"{self.base_url}/api/agent/skills"
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_skill(self, skill_name: str) -> Dict[str, Any]:
        """获取技能详情"""
        url = f"{self.base_url}/api/agent/skills/{skill_name}"
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def refresh_skills(self) -> Dict[str, Any]:
        """刷新技能列表"""
        url = f"{self.base_url}/api/agent/skills/refresh"
        response = requests.post(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ==================== Memories ====================

    def set_memory(
        self,
        session_id: str,
        key: str,
        value: Any,
        memory_type: str = "fact"
    ) -> Dict[str, Any]:
        """设置记忆"""
        url = f"{self.base_url}/api/agent/sessions/{session_id}/memories"
        payload = {
            "key": key,
            "value": value,
            "memory_type": memory_type
        }
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_memories(self, session_id: str) -> Dict[str, Any]:
        """获取记忆"""
        url = f"{self.base_url}/api/agent/sessions/{session_id}/memories"
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ==================== Health ====================

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        url = f"{self.base_url}/health"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    # 使用示例
    client = AgentClient()

    # 健康检查
    print("=== 健康检查 ===")
    try:
        health = client.health_check()
        print(f"状态: {health['status']}")
        print(f"日期: {health.get('date', 'N/A')}")
    except Exception as e:
        print(f"健康检查失败: {e}")
        print("请确保 Agent 服务已启动")
        exit(1)

    # 列出技能
    print("\n=== 可用技能 ===")
    skills = client.list_skills()
    for skill in skills.get("skills", []):
        print(f"  - {skill['name']}: {skill['description'][:50]}...")

    # 流式对话示例
    print("\n=== 流式对话 ===")
    message = "北京天气怎么样"
    print(f"用户: {message}")
    print("Agent: ", end="", flush=True)

    for event in client.stream_complete(message):
        event_type = event.get("event_type")
        if event_type == "answer":
            print(event.get("content", ""), end="", flush=True)
        elif event_type == "thinking":
            print(f"\n[思考] {event.get('content', '')}")
        elif event_type == "skill_call":
            print(f"\n[调用技能] {event.get('skill_name', '')}")
        elif event_type == "done":
            print(f"\n[完成] 使用技能: {event.get('result', {}).get('skills_used', [])}")
        elif event_type == "error":
            print(f"\n[错误] {event.get('error', '')}")
        else:
            print(f"\n[其他事件] {event}")

    print()
