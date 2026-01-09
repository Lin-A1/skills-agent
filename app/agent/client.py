"""
Agent Service Client
Provides a simple client for interacting with the Agent Service API
"""
import json
import os
from typing import Any, AsyncGenerator, Dict, Optional

import httpx


def get_default_base_url() -> str:
    """Get the default base URL from environment or use default"""
    host = os.getenv("AGENT_SERVICE_HOST", "localhost")
    port = os.getenv("AGENT_SERVICE_PORT", "8009")
    return f"http://{host}:{port}"


class AgentClient:
    """
    Agent 服务客户端
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 300.0  # 5 分钟超时，适应 deepsearch 等长时间操作
    ):
        """
        初始化客户端
        
        Args:
            base_url: 服务基础 URL，默认从环境变量读取
            timeout: 请求超时时间（秒）
        """
        self.base_url = (base_url or get_default_base_url()).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None
    
    @property
    def client(self) -> httpx.Client:
        """获取同步 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client
    
    @property
    def async_client(self) -> httpx.AsyncClient:
        """获取异步 HTTP 客户端"""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._async_client
    
    # ==================== Agent 执行 ====================
    
    def run(
        self,
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        max_iterations: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        同步执行 Agent 任务
        
        Args:
            message: 用户消息
            session_id: 会话 ID
            user_id: 用户 ID
            max_iterations: 最大迭代次数
            **kwargs: 其他参数
            
        Returns:
            Agent 响应
        """
        response = self.client.post(
            "/api/agent/run/sync",
            json={
                "message": message,
                "session_id": session_id,
                "user_id": user_id,
                "max_iterations": max_iterations,
                "stream": False,
                **kwargs
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def async_run(
        self,
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        max_iterations: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        异步执行 Agent 任务
        """
        response = await self.async_client.post(
            "/api/agent/run/sync",
            json={
                "message": message,
                "session_id": session_id,
                "user_id": user_id,
                "max_iterations": max_iterations,
                "stream": False,
                **kwargs
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def stream_run(
        self,
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        max_iterations: int = 10,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行 Agent 任务
        
        Args:
            message: 用户消息
            session_id: 会话 ID
            user_id: 用户 ID
            max_iterations: 最大迭代次数
            **kwargs: 其他参数
            
        Yields:
            SSE 事件
        """
        async with self.async_client.stream(
            "POST",
            "/api/agent/run",
            json={
                "message": message,
                "session_id": session_id,
                "user_id": user_id,
                "max_iterations": max_iterations,
                "stream": True,
                **kwargs
            }
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    yield json.loads(data)
    
    # ==================== 工具管理 ====================
    
    def list_tools(self) -> Dict[str, Any]:
        """获取可用工具列表"""
        response = self.client.get("/api/agent/tools")
        response.raise_for_status()
        return response.json()
    
    def get_tool(self, tool_name: str) -> Dict[str, Any]:
        """获取工具详情"""
        response = self.client.get(f"/api/agent/tools/{tool_name}")
        response.raise_for_status()
        return response.json()
    
    # ==================== 会话管理 ====================
    
    def list_sessions(
        self, 
        user_id: str, 
        limit: int = 20
    ) -> Dict[str, Any]:
        """获取用户会话列表"""
        response = self.client.get(
            "/api/agent/sessions",
            params={"user_id": user_id, "limit": limit}
        )
        response.raise_for_status()
        return response.json()
    
    def get_session(
        self, 
        session_id: str, 
        user_id: str = "anonymous"
    ) -> Dict[str, Any]:
        """获取会话详情"""
        response = self.client.get(
            f"/api/agent/sessions/{session_id}",
            params={"user_id": user_id}
        )
        response.raise_for_status()
        return response.json()
    
    def delete_session(self, session_id: str) -> Dict[str, Any]:
        """删除会话"""
        response = self.client.delete(f"/api/agent/sessions/{session_id}")
        response.raise_for_status()
        return response.json()
    
    # ==================== 健康检查 ====================
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        response = self.client.get("/health")
        response.raise_for_status()
        return response.json()
    
    # ==================== 资源管理 ====================
    
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
    
    async def demo():
        async with AgentClient() as client:
            # 健康检查
            print("Health:", client.health_check())
            
            # 获取工具列表
            tools = client.list_tools()
            print(f"Available tools: {[t['name'] for t in tools['tools']]}\n")
            
            # 流式执行
            print("=" * 60)
            print("🤖 Agent 执行演示")
            print("=" * 60)
            
            session_id = None
            agent_steps = []
            final_answer = ""
            
            async for event in client.stream_run(
                message="南宁的天气怎么样",
                user_id="test_user"
            ):
                event_type = event.get('type')
                event_data = event.get('data')
                
                # 提取 session_id
                if event_type == 'intent' and isinstance(event_data, dict):
                    session_id = event_data.get('session_id')
                    if session_id:
                        print(f"\n📝 会话 ID: {session_id}")
                        print(f"💭 意图: {event_data.get('message', '')[:50]}...")
                        print(f"🎯 复杂度: {event_data.get('complexity', 'unknown')}\n")
                
                # 思考过程
                elif event_type == 'thought':
                    print(f"\n💡 思考: {event_data[:100]}..." if len(str(event_data)) > 100 else f"\n💡 思考: {event_data}")
                    agent_steps.append(('thought', event_data))
                
                # 行动
                elif event_type == 'action':
                    tool = event_data.get('tool', 'unknown')
                    print(f"🔧 调用工具: {tool}")
                    if event_data.get('arguments'):
                        args_str = json.dumps(event_data['arguments'], ensure_ascii=False, indent=2)
                        print(f"   参数: {args_str[:150]}..." if len(args_str) > 150 else f"   参数: {args_str}")
                    agent_steps.append(('action', event_data))
                
                # 观察结果
                elif event_type == 'observation':
                    success = event_data.get('success', False)
                    status_icon = "✅" if success else "❌"
                    print(f"{status_icon} 执行结果: {'成功' if success else '失败'}")
                    if not success and event_data.get('error'):
                        print(f"   错误: {event_data['error'][:100]}")
                    elif success and event_data.get('result'):
                        result_str = str(event_data['result'])
                        print(f"   结果: {result_str[:150]}..." if len(result_str) > 150 else f"   结果: {result_str}")
                    agent_steps.append(('observation', event_data))
                
                # 最终答案
                elif event_type == 'final_answer':
                    final_answer = event_data
                    print(final_answer, end='')
                
                # 完成
                elif event_type == 'complete':
                    iterations = event_data.get('iterations', 0)
                    total_time = event_data.get('total_time', 0)
                    tools_used = event_data.get('tools_used', [])
                    print(f"\n✨ 完成!")
                    print(f"   迭代次数: {iterations}")
                    print(f"   总耗时: {total_time:.2f}秒")
                    print(f"   使用工具: {', '.join(tools_used) if tools_used else '无'}")
                
                # 错误
                elif event_type == 'error':
                    print(f"\n❌ 错误: {event_data}")
            
            print(f"\n总计收集了 {len(agent_steps)} 个执行步骤")
    
    asyncio.run(demo())
