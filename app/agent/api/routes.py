"""
Agent API Routes
FastAPI endpoints for Agent service
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..schemas.agent import (
    AgentRequest,
    AgentResponse,
    ToolInfo
)
from ..services.agent_service import agent_service
from ..services.stream_handler import stream_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


# ==================== Agent 执行 ====================

@router.post("/run")
async def run_agent(request: AgentRequest):
    """
    执行 Agent 任务
    
    - **message**: 用户消息/任务描述
    - **session_id**: 会话ID（可选，不提供则创建新会话）
    - **stream**: 是否流式返回（默认 True）
    - **max_iterations**: 最大迭代次数（默认 10）
    
    流式返回 SSE 格式：
    ```
    data: {"type": "intent", "data": {...}}
    data: {"type": "thought", "data": "..."}
    data: {"type": "action", "data": {"tool": "...", ...}}
    data: {"type": "observation", "data": {...}}
    data: {"type": "final_answer", "data": "..."}
    data: [DONE]
    ```
    """
    try:
        if request.stream:
            # 流式响应
            return stream_handler.create_sse_response(
                agent_service.run_agent(request)
            )
        else:
            # 非流式响应
            response = await agent_service.run_agent_sync(request)
            return response
            
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/sync", response_model=AgentResponse)
async def run_agent_sync(request: AgentRequest):
    """
    同步执行 Agent 任务（等待完成后返回完整结果）
    """
    try:
        request.stream = False
        response = await agent_service.run_agent_sync(request)
        return response
    except Exception as e:
        logger.error(f"Agent sync execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 工具管理 ====================

@router.get("/tools")
async def list_tools():
    """
    获取所有可用工具列表
    """
    tools = agent_service.get_available_tools()
    return {
        "tools": tools,
        "count": len(tools)
    }


@router.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """
    获取指定工具的详细信息
    """
    tools = agent_service.get_available_tools()
    tool = next((t for t in tools if t["name"] == tool_name), None)
    
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    
    return tool


# ==================== 会话管理 ====================

@router.get("/sessions")
async def list_sessions(
    user_id: str = Query(..., description="用户ID"),
    limit: int = Query(20, description="最大返回数量"),
    include_archived: bool = Query(False, description="是否包含已归档会话")
):
    """
    获取用户的会话列表
    """
    try:
        sessions = agent_service.list_user_sessions(
            user_id=user_id,
            limit=limit,
            include_archived=include_archived
        )
        return {
            "sessions": sessions,
            "count": len(sessions)
        }
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user_id: str = Query("anonymous", description="用户ID"),
    limit: Optional[int] = Query(None, description="限制消息数量")
):
    """
    获取会话详情和消息历史
    """
    try:
        session_data = agent_service.get_session_history(
            session_id=session_id,
            user_id=user_id,
            limit=limit
        )
        return session_data
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    删除指定会话
    """
    success = agent_service.delete_session(session_id)
    if success:
        return {"success": True, "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def delete_message(
    session_id: str, 
    message_id: str,
    include_following: bool = Query(False, description="是否同时删除之后的消息")
):
    """
    删除消息（支持级联删除）
    """
    success = agent_service.delete_message(session_id, message_id, include_following)
    if success:
        return {"success": True, "message_id": message_id}
    else:
        raise HTTPException(status_code=404, detail=f"Message '{message_id}' not found or delete failed")


@router.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    """
    清空会话消息（保留会话记录）
    """
    success = agent_service.clear_session(session_id)
    if success:
        return {"success": True, "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


# ==================== 图片分析 ====================

class ImageAnalysisRequest(BaseModel):
    """图片分析请求"""
    images: List[str]  # URL、本地路径或 base64
    message: str  # 用户消息/需求
    user_id: Optional[str] = None


@router.post("/analyze/image")
async def analyze_image(request: ImageAnalysisRequest):
    """
    使用 OCR + LLM 分析图片内容
    
    - **images**: 图片列表（URL 或本地路径或 base64 数据）
    - **message**: 用户需求/问题
    - **user_id**: 用户ID（可选）
    
    返回格式：
    ```json
    {
        "success": true,
        "analysis": "图片分析结果...",
        "ocr_text": "OCR 识别的文字",
        "model": "qwen-plus",
        "images_count": 1
    }
    ```
    """
    try:
        result = await agent_service.analyze_images_standalone(
            images=request.images,
            user_message=request.message,
            user_id=request.user_id
        )
        return result
    except Exception as e:
        logger.error(f"Image analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/extract")
async def extract_from_image(request: ImageAnalysisRequest):
    """
    从图片中提取结构化信息
    
    返回 JSON 格式的提取结果，包括：
    - summary: 摘要
    - extracted_text: 文字内容
    - key_data: 关键数据
    - relevant_info: 相关信息
    """
    try:
        from ..services.vlm_service import vlm_service
        
        result = await vlm_service.extract_information(
            images=request.images,
            user_context=request.message,
            extraction_focus=["文字内容", "关键数据", "表格信息", "可视化元素"]
        )
        
        return result
    except Exception as e:
        logger.error(f"Image extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
