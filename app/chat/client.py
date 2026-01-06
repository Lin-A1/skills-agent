"""
Chat Service Client
Provides a simple client for interacting with the Chat Service API
"""
import httpx
from typing import Optional, Dict, Any, List, AsyncGenerator
import json


class ChatClient:
    """
    聊天服务客户端
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8006",
        timeout: float = 60.0
    ):
        """
        初始化客户端
        
        Args:
            base_url: 服务基础URL
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None
    
    @property
    def client(self) -> httpx.Client:
        """获取同步HTTP客户端"""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client
    
    @property
    def async_client(self) -> httpx.AsyncClient:
        """获取异步HTTP客户端"""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._async_client
    
    # ==================== Session Methods ====================
    
    def create_session(
        self,
        title: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """
        创建新会话
        
        Args:
            title: 会话标题
            model: 模型名称
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大输出tokens
            
        Returns:
            会话信息
        """
        response = self.client.post(
            "/api/chat/sessions",
            json={
                "title": title,
                "model": model,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        )
        response.raise_for_status()
        return response.json()
    
    def list_sessions(
        self,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取会话列表
        
        Args:
            page: 页码
            page_size: 每页数量
            user_id: 用户ID过滤
            
        Returns:
            会话列表
        """
        params = {"page": page, "page_size": page_size}
        if user_id:
            params["user_id"] = user_id
        
        response = self.client.get("/api/chat/sessions", params=params)
        response.raise_for_status()
        return response.json()
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        """获取会话详情"""
        response = self.client.get(f"/api/chat/sessions/{session_id}")
        response.raise_for_status()
        return response.json()
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        response = self.client.delete(f"/api/chat/sessions/{session_id}")
        response.raise_for_status()
        return True
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取会话消息"""
        params = {}
        if limit:
            params["limit"] = limit
        
        response = self.client.get(
            f"/api/chat/sessions/{session_id}/messages",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    # ==================== Chat Methods ====================
    
    def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        发送聊天消息（同步）
        
        Args:
            message: 用户消息
            session_id: 会话ID（可选，不提供则创建新会话）
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出tokens
            
        Returns:
            聊天响应
        """
        response = self.client.post(
            "/api/chat/completions",
            json={
                "message": message,
                "session_id": session_id,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def async_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        发送聊天消息（异步）
        """
        response = await self.async_client.post(
            "/api/chat/completions",
            json={
                "message": message,
                "session_id": session_id,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def stream_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式聊天
        
        Args:
            message: 用户消息
            session_id: 会话ID
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出tokens
            
        Yields:
            流式响应块
        """
        async with self.async_client.stream(
            "POST",
            "/api/chat/completions",
            json={
                "message": message,
                "session_id": session_id,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True
            }
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    yield json.loads(data)
    
    def close(self):
        """关闭客户端连接"""
        if self._client:
            self._client.close()
            self._client = None
    
    async def aclose(self):
        """异步关闭客户端连接"""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()


# 使用示例
if __name__ == "__main__":
    import asyncio
    
    # 同步使用示例
    def sync_example():
        with ChatClient() as client:
            # 创建会话
            session = client.create_session(
                title="测试会话",
                system_prompt="你是一个友好的AI助手。"
            )
            print(f"Created session: {session['id']}")
            
            # 发送消息
            response = client.chat(
                message="你好，请介绍一下你自己。",
                session_id=session['id']
            )
            print(f"Assistant: {response['choices'][0]['message']['content']}")
            
            # 获取消息历史
            messages = client.get_messages(session['id'])
            print(f"Total messages: {messages['total']}")
    
    # 异步流式使用示例
    async def async_stream_example():
        async with ChatClient() as client:
            session = await client.async_client.post(
                "/api/chat/sessions",
                json={"title": "流式测试"}
            )
            session_id = session.json()['id']
            
            print("Streaming response: ", end="")
            async for chunk in client.stream_chat(
                message="你是谁。",
                session_id=session_id
            ):
                if chunk['choices'][0]['delta'].get('content'):
                    print(chunk['choices'][0]['delta']['content'], end="", flush=True)
            print()
    
    # 运行示例
    print("=== Sync Example ===")
    sync_example()
    
    print("\n=== Async Stream Example ===")
    asyncio.run(async_stream_example())
