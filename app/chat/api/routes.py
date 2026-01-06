"""
API Routes for Chat Application
Provides RESTful endpoints compatible with OpenAI API format
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession
import json

from ..database import get_db
from ..schemas import (
    SessionCreate,
    SessionUpdate,
    SessionResponse,
    SessionListResponse,
    MessageResponse,
    MessageListResponse,
    ChatRequest,
    ChatResponse
)
from ..services import ChatService, chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


# ==================== Session Endpoints ====================

@router.post("/sessions", response_model=SessionResponse, summary="创建新会话")
async def create_session(
    data: SessionCreate,
    db: DBSession = Depends(get_db)
):
    """
    创建新的聊天会话
    
    - **title**: 会话标题（可选）
    - **model**: 使用的模型名称（可选，默认为配置中的模型）
    - **system_prompt**: 系统提示词（可选）
    - **temperature**: 温度参数，0-2（可选，默认0.7）
    - **max_tokens**: 最大输出tokens（可选，默认2048）
    """
    session = chat_service.create_session(db, data)
    return SessionResponse(**session.to_dict())


@router.get("/sessions", response_model=SessionListResponse, summary="获取会话列表")
async def list_sessions(
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    include_archived: bool = Query(False, description="是否包含已归档会话"),
    db: DBSession = Depends(get_db)
):
    """
    获取会话列表，支持分页
    """
    sessions, total = chat_service.list_sessions(
        db, user_id, page, page_size, include_archived
    )
    
    return SessionListResponse(
        sessions=[SessionResponse(**s.to_dict()) for s in sessions],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse, summary="获取会话详情")
async def get_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """
    获取指定会话的详细信息
    """
    session = chat_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(**session.to_dict())


@router.patch("/sessions/{session_id}", response_model=SessionResponse, summary="更新会话")
async def update_session(
    session_id: str,
    data: SessionUpdate,
    db: DBSession = Depends(get_db)
):
    """
    更新会话信息
    """
    session = chat_service.update_session(db, session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(**session.to_dict())


@router.delete("/sessions/{session_id}", summary="删除会话")
async def delete_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """
    删除指定会话及其所有消息
    """
    success = chat_service.delete_session(db, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": "Session deleted successfully"}


# ==================== Message Endpoints ====================

@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse, summary="获取会话消息")
async def get_session_messages(
    session_id: str,
    limit: Optional[int] = Query(None, ge=1, le=100, description="最大消息数量"),
    db: DBSession = Depends(get_db)
):
    """
    获取指定会话的消息历史
    """
    # 先检查会话是否存在
    session = chat_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = chat_service.get_session_messages(db, session_id, limit)
    
    return MessageListResponse(
        messages=[MessageResponse(**m.to_dict()) for m in messages],
        total=len(messages)
    )


@router.delete("/sessions/{session_id}/messages/{message_id}", summary="删除消息")
async def delete_message(
    session_id: str,
    message_id: str,
    db: DBSession = Depends(get_db)
):
    """
    删除指定会话中的特定消息
    """
    from uuid import UUID
    
    # 检查会话是否存在
    session = chat_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 删除消息
    try:
        msg_uuid = UUID(message_id)
        from ..database import Message
        message = db.query(Message).filter(
            Message.id == msg_uuid,
            Message.session_id == UUID(session_id)
        ).first()
        
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        db.delete(message)
        db.commit()
        
        return {"message": "Message deleted successfully"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID format")


# ==================== Chat Completion Endpoints ====================

@router.post("/completions", summary="聊天完成")
async def chat_completion(
    request: ChatRequest,
    db: DBSession = Depends(get_db)
):
    """
    聊天完成接口（兼容OpenAI格式）
    
    支持两种使用方式：
    1. 简化形式：提供 session_id 和 message
    2. 完整形式：提供 messages 列表
    
    支持流式和非流式输出：
    - stream=false：返回完整响应（默认）
    - stream=true：返回Server-Sent Events流
    """
    try:
        if request.stream:
            # 流式响应
            async def generate():
                session_id = None
                task_triggered = False
                async for chunk in chat_service.async_stream_chat(db, request):
                    if not session_id and chunk.get("session_id"):
                        session_id = chunk["session_id"]
                        if not task_triggered:
                            import asyncio
                            logger.info(f"Triggering background title generation for {session_id}")
                            asyncio.create_task(chat_service.generate_session_title(session_id))
                            task_triggered = True
                            
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            response = await chat_service.async_chat(db, request)
            
            # 触发后台生成标题任务
            if response.get("session_id"):
                import asyncio
                asyncio.create_task(chat_service.generate_session_title(response["session_id"]))
                
            return ChatResponse(**response)
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ==================== Utility Endpoints ====================

@router.post("/sessions/{session_id}/clear", summary="清空会话消息")
async def clear_session_messages(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """
    清空指定会话的所有消息，但保留会话本身
    """
    session = chat_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 删除所有消息
    from ..database import Message
    from uuid import UUID
    
    db.query(Message).filter(Message.session_id == UUID(session_id)).delete()
    db.commit()
    
    return {"message": "Session messages cleared successfully"}


@router.post("/sessions/{session_id}/archive", summary="归档会话")
async def archive_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """
    归档指定会话
    """
    session = chat_service.update_session(
        db, session_id, 
        SessionUpdate(is_archived=True)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": "Session archived successfully"}


@router.post("/sessions/{session_id}/unarchive", summary="取消归档会话")
async def unarchive_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """
    取消归档指定会话
    """
    session = chat_service.update_session(
        db, session_id,
        SessionUpdate(is_archived=False)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": "Session unarchived successfully"}
