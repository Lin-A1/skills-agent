"""
API Routes for Agent Application
Provides RESTful endpoints for Agent interaction
"""
import logging
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..database import get_db
from sqlalchemy.orm import Session as DBSession

from ..schemas import (
    AgentRequest, AgentResponse, AgentEvent,
    SessionCreate, SessionUpdate, SessionResponse, SessionListResponse,
    MessageListResponse, MemoryCreate, MemoryResponse, MemoryListResponse,
    SkillListResponse, SkillDetail
)
from ..services import AgentService, agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


# ==================== Session Endpoints ====================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    data: SessionCreate,
    db: DBSession = Depends(get_db)
):
    """
    创建新的 Agent 会话
    
    - **title**: 会话标题（可选）
    - **model**: 使用的模型名称（可选）
    - **system_prompt**: 系统提示词（可选）
    - **temperature**: 温度参数（可选，默认 0.3）
    """
    return agent_service.create_session(db, data)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    include_archived: bool = Query(False, description="是否包含已归档会话"),
    db: DBSession = Depends(get_db)
):
    """获取会话列表，支持分页"""
    sessions, total = agent_service.list_sessions(
        db, user_id, page, page_size, include_archived
    )
    return SessionListResponse(
        sessions=sessions,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """获取指定会话的详细信息"""
    session = agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.put("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    data: SessionUpdate,
    db: DBSession = Depends(get_db)
):
    """更新会话信息"""
    session = agent_service.update_session(db, session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """删除指定会话及其所有消息"""
    if not agent_service.delete_session(db, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


# ==================== Message Endpoints ====================

@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
async def get_session_messages(
    session_id: str,
    limit: Optional[int] = Query(None, ge=1, le=100, description="最大消息数量"),
    db: DBSession = Depends(get_db)
):
    """获取指定会话的消息历史"""
    session = agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = agent_service.get_session_messages(db, session_id, limit)
    return MessageListResponse(messages=messages, total=len(messages))


@router.delete("/sessions/{session_id}/messages")
async def clear_session_messages(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """清空指定会话的所有消息"""
    from ..database import AgentMessage
    
    session = agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    db.query(AgentMessage).filter(
        AgentMessage.session_id == session_id
    ).delete()
    db.commit()
    
    return {"status": "cleared", "session_id": session_id}

    return {"status": "cleared", "session_id": session_id}


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def delete_message(
    session_id: str,
    message_id: str,
    db: DBSession = Depends(get_db)
):
    """删除指定会话中的单条消息"""
    if not agent_service.delete_message(db, session_id, message_id):
        raise HTTPException(status_code=404, detail="Message not found")
    
    return {"status": "deleted", "session_id": session_id, "message_id": message_id}
# ==================== Agent Completion Endpoints ====================

@router.post("/completions")
async def agent_completion(
    request: AgentRequest,
    db: DBSession = Depends(get_db)
):
    """
    Agent 完成接口
    
    支持两种输出模式：
    - stream=false：返回完整响应（默认）
    - stream=true：返回 Server-Sent Events 流
    
    Agent 可以在一次回答中多次调用技能（Skills），
    通过读取 SKILL.md 文档并使用 sandbox 执行代码。
    """
    if request.stream:
        # 流式输出
        async def generate():
            async for event in agent_service.async_stream_agent(db, request):
                event_data = event.model_dump()
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
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
        # 非流式输出
        response = await agent_service.async_agent(db, request)
        return response


# ==================== Memory Endpoints ====================

@router.post("/sessions/{session_id}/memories", response_model=MemoryResponse)
async def set_memory(
    session_id: str,
    data: MemoryCreate,
    db: DBSession = Depends(get_db)
):
    """设置会话记忆"""
    session = agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return agent_service.set_memory(db, session_id, data)


@router.get("/sessions/{session_id}/memories", response_model=MemoryListResponse)
async def get_session_memories(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """获取会话记忆"""
    session = agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    memories = agent_service.get_session_memories(db, session_id)
    return MemoryListResponse(memories=memories, total=len(memories))


@router.delete("/sessions/{session_id}/memories/{key}")
async def delete_memory(
    session_id: str,
    key: str,
    db: DBSession = Depends(get_db)
):
    """删除指定记忆"""
    from ..database import AgentMemory
    from ..core import get_context_manager
    
    session = agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 从数据库删除
    deleted = db.query(AgentMemory).filter(
        AgentMemory.session_id == session_id,
        AgentMemory.key == key
    ).delete()
    db.commit()
    
    # 从内存删除
    get_context_manager().delete_memory(session_id, key)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"status": "deleted", "key": key}


# ==================== Skill Endpoints ====================

@router.get("/skills", response_model=SkillListResponse)
async def list_skills():
    """列出所有可用技能"""
    skills = agent_service.list_skills()
    return SkillListResponse(
        skills=skills,
        total=len(skills)
    )


@router.get("/skills/{skill_name}", response_model=SkillDetail)
async def get_skill(skill_name: str):
    """获取指定技能的详细信息"""
    from ..core import get_skill_registry
    
    registry = get_skill_registry()
    skill = registry.get_skill(skill_name)
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return SkillDetail(
        name=skill.name,
        description=skill.description,
        path=skill.path,
        content=skill.content or ""
    )


@router.post("/skills/refresh")
async def refresh_skills():
    """刷新技能列表"""
    count = agent_service.refresh_skills()
    return {"status": "refreshed", "skill_count": count}


# ==================== Utility Endpoints ====================

@router.post("/sessions/{session_id}/archive")
async def archive_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """归档指定会话"""
    session = agent_service.update_session(
        db, session_id,
        SessionUpdate(is_archived=True)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "archived", "session_id": session_id}


@router.post("/sessions/{session_id}/unarchive")
async def unarchive_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """取消归档指定会话"""
    session = agent_service.update_session(
        db, session_id,
        SessionUpdate(is_archived=False)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "unarchived", "session_id": session_id}
