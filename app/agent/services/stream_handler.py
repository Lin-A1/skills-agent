"""
Stream Handler - SSE Streaming Response
Converts Agent events to Server-Sent Events format
"""
import json
import logging
from typing import Any, AsyncGenerator, Dict

from fastapi.responses import StreamingResponse

from ..schemas.agent import AgentEvent

logger = logging.getLogger(__name__)


class StreamHandler:
    """
    流式响应处理器
    
    将 Agent 事件转换为 SSE (Server-Sent Events) 格式
    """
    
    @staticmethod
    def format_sse_event(event: AgentEvent) -> str:
        """
        格式化单个 SSE 事件
        
        Args:
            event: Agent 事件
            
        Returns:
            SSE 格式的字符串
        """
        data = {
            "event_id": event.event_id,
            "type": event.type,
            "data": event.data,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None
        }
        
        # 添加可选字段
        if event.iteration is not None:
            data["iteration"] = event.iteration
        if event.tool_name is not None:
            data["tool_name"] = event.tool_name
        if event.execution_time is not None:
            data["execution_time"] = event.execution_time
        
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    
    @staticmethod
    async def create_event_generator(
        agent_generator: AsyncGenerator[AgentEvent, None]
    ) -> AsyncGenerator[str, None]:
        """
        创建 SSE 事件生成器
        
        Args:
            agent_generator: Agent 事件生成器
            
        Yields:
            SSE 格式的字符串
        """
        try:
            async for event in agent_generator:
                yield StreamHandler.format_sse_event(event)
        except Exception as e:
            # 发送错误事件
            error_event = AgentEvent(
                type="error",
                data={"error": str(e)}
            )
            yield StreamHandler.format_sse_event(error_event)
        finally:
            # 发送结束标记
            yield "data: [DONE]\n\n"
    
    @staticmethod
    def create_sse_response(
        agent_generator: AsyncGenerator[AgentEvent, None]
    ) -> StreamingResponse:
        """
        创建 SSE StreamingResponse
        
        Args:
            agent_generator: Agent 事件生成器
            
        Returns:
            FastAPI StreamingResponse
        """
        return StreamingResponse(
            StreamHandler.create_event_generator(agent_generator),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
            }
        )
    
    @staticmethod
    def format_non_stream_response(
        events: list[AgentEvent]
    ) -> Dict[str, Any]:
        """
        将事件列表格式化为非流式响应
        
        Args:
            events: Agent 事件列表
            
        Returns:
            格式化的响应字典
        """
        response = {
            "events": [],
            "final_answer": None,
            "iterations": 0,
            "tools_used": [],
            "total_time": None
        }
        
        for event in events:
            response["events"].append({
                "type": event.type,
                "data": event.data,
                "iteration": event.iteration,
                "tool_name": event.tool_name
            })
            
            # 提取最终答案
            if event.type == "final_answer":
                response["final_answer"] = event.data
            
            # 提取完成信息
            if event.type == "complete" and isinstance(event.data, dict):
                response["iterations"] = event.data.get("iterations", 0)
                response["tools_used"] = event.data.get("tools_used", [])
                response["total_time"] = event.data.get("total_time")
        
        return response


# 全局流处理器实例
stream_handler = StreamHandler()
