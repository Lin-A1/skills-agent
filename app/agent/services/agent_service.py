"""
Agent Service - Business Logic Layer
Handles agent sessions, messages, and orchestrates the agent engine
"""
import asyncio
import logging
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session as DBSession

from ..config import settings
from ..schemas import (
    AgentRequest, AgentResponse, AgentEvent, AgentEventType,
    SessionCreate, SessionUpdate, SessionResponse,
    MessageResponse, MemoryCreate, MemoryResponse,
    UsageInfo
)
from ..core import get_agent_engine, get_context_manager, get_skill_registry
from .llm_service import LLMService, llm_service

logger = logging.getLogger(__name__)


class AgentService:
    """
    Agent 服务类
    处理会话管理、消息存储和 Agent 执行编排
    """

    def __init__(self, llm: Optional[LLMService] = None):
        """
        初始化 Agent 服务
        
        Args:
            llm: LLM 服务实例，默认使用全局实例
        """
        self.llm = llm or llm_service
        self._engine = get_agent_engine()
        self._engine.set_llm_service(self.llm)
        self._context_manager = get_context_manager()
        self._skill_registry = get_skill_registry()
        self._executor = ThreadPoolExecutor(max_workers=4)
        
        logger.info("AgentService initialized")

    # ==================== Session Management ====================

    def create_session(
        self,
        db: DBSession,
        data: SessionCreate
    ) -> SessionResponse:
        """
        创建新会话
        
        Args:
            db: 数据库会话
            data: 会话创建数据
            
        Returns:
            创建的会话响应
        """
        from ..database import AgentSession
        
        session = AgentSession(
            id=str(uuid.uuid4()),
            title=data.title or "新的 Agent 对话",
            model=data.model or settings.AGENT_LLM_MODEL_NAME,
            system_prompt=data.system_prompt,
            temperature=data.temperature or settings.DEFAULT_TEMPERATURE,
            max_tokens=data.max_tokens or settings.DEFAULT_MAX_TOKENS,
            user_id=data.user_id,
            extra_data=data.extra_data
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        
        logger.info(f"Created agent session: {session.id}")
        
        return self._session_to_response(session)

    def get_session(
        self,
        db: DBSession,
        session_id: str
    ) -> Optional[SessionResponse]:
        """获取会话"""
        from ..database import AgentSession
        
        session = db.query(AgentSession).filter(
            AgentSession.id == session_id
        ).first()
        
        if session:
            return self._session_to_response(session)
        return None

    def update_session(
        self,
        db: DBSession,
        session_id: str,
        data: SessionUpdate
    ) -> Optional[SessionResponse]:
        """更新会话"""
        from ..database import AgentSession
        
        session = db.query(AgentSession).filter(
            AgentSession.id == session_id
        ).first()
        
        if not session:
            return None
        
        # 更新非 None 字段
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(session, key, value)
        
        session.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(session)
        
        return self._session_to_response(session)

    def delete_session(
        self,
        db: DBSession,
        session_id: str
    ) -> bool:
        """删除会话"""
        from ..database import AgentSession, AgentMessage, AgentMemory
        
        session = db.query(AgentSession).filter(
            AgentSession.id == session_id
        ).first()
        
        if not session:
            return False
        
        # 删除相关消息和记忆
        db.query(AgentMessage).filter(
            AgentMessage.session_id == session_id
        ).delete()
        db.query(AgentMemory).filter(
            AgentMemory.session_id == session_id
        ).delete()
        
        db.delete(session)
        db.commit()
        
        # 清理内存中的记忆
        self._context_manager.clear_session_memories(session_id)
        
        logger.info(f"Deleted agent session: {session_id}")
        return True

    def list_sessions(
        self,
        db: DBSession,
        user_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False
    ) -> Tuple[List[SessionResponse], int]:
        """列出会话"""
        from ..database import AgentSession
        
        query = db.query(AgentSession)
        
        if user_id:
            query = query.filter(AgentSession.user_id == user_id)
        if not include_archived:
            query = query.filter(AgentSession.is_archived == False)
        
        total = query.count()
        
        sessions = query.order_by(AgentSession.updated_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
        
        return [self._session_to_response(s) for s in sessions], total

    def _session_to_response(self, session) -> SessionResponse:
        """转换会话为响应格式"""
        from ..database import AgentMessage
        
        return SessionResponse(
            id=str(session.id),
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            model=session.model,
            system_prompt=session.system_prompt,
            temperature=session.temperature,
            max_tokens=session.max_tokens,
            is_active=session.is_active,
            is_archived=session.is_archived,
            user_id=session.user_id,
            extra_data=session.extra_data,
            message_count=0  # 可选：添加消息计数查询
        )

    # ==================== Message Management ====================

    def add_message(
        self,
        db: DBSession,
        session_id: str,
        role: str,
        content: str,
        event_type: Optional[str] = None,
        skill_name: Optional[str] = None,
        execution_result: Optional[Dict[str, Any]] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> MessageResponse:
        """添加消息"""
        from ..database import AgentMessage, AgentSession
        
        message = AgentMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            event_type=event_type,
            skill_name=skill_name,
            execution_result=execution_result,
            extra_data=extra_data
        )
        
        db.add(message)
        
        # 更新会话时间
        session = db.query(AgentSession).filter(
            AgentSession.id == session_id
        ).first()
        if session:
            session.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(message)
        
        return self._message_to_response(message)

    def get_session_messages(
        self,
        db: DBSession,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[MessageResponse]:
        """获取会话消息"""
        from ..database import AgentMessage
        
        query = db.query(AgentMessage).filter(
            AgentMessage.session_id == session_id
        ).order_by(AgentMessage.created_at.asc())
        
        if limit:
            query = query.limit(limit)
        
        messages = query.all()
        return [self._message_to_response(m) for m in messages]

    def _message_to_response(self, message) -> MessageResponse:
        """转换消息为响应格式"""
        return MessageResponse(
            id=str(message.id),
            session_id=str(message.session_id),
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            event_type=message.event_type,
            skill_name=message.skill_name,
            execution_result=message.execution_result,
            extra_data=message.extra_data
        )

    def delete_message(
        self,
        db: DBSession,
        session_id: str,
        message_id: str
    ) -> bool:
        """删除指定消息"""
        from ..database import AgentMessage
        
        message = db.query(AgentMessage).filter(
            AgentMessage.session_id == session_id,
            AgentMessage.id == message_id
        ).first()
        
        if not message:
            return False
            
        db.delete(message)
        db.commit()
        return True

    def build_context_messages(
        self,
        db: DBSession,
        session_id: str
    ) -> List[Dict[str, str]]:
        """构建上下文消息列表"""
        messages = self.get_session_messages(db, session_id)
        return [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant", "system")
        ]

    # ==================== Agent Execution ====================

    async def async_stream_agent(
        self,
        db: DBSession,
        request: AgentRequest
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        异步流式执行 Agent
        
        Args:
            db: 数据库会话
            request: Agent 请求
            
        Yields:
            AgentEvent 事件流
        """
        session_id = request.session_id
        
        # 如果没有会话ID，创建新会话
        if not session_id:
            try:
                session_data = SessionCreate(
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    user_id=request.user_id
                )
                session_response = self.create_session(db, session_data)
                session_id = session_response.id
                logger.info(f"Created new session: {session_id}")
            except Exception as e:
                logger.error(f"Failed to create session: {e}", exc_info=True)
                yield AgentEvent(
                    event_type=AgentEventType.ERROR,
                    error=f"Failed to create session: {str(e)}"
                )
                return
        
        # 保存用户消息
        if not request.skip_save_user_message:
            try:
                self.add_message(
                    db=db,
                    session_id=session_id,
                    role="user",
                    content=request.message
                )
            except Exception as e:
                logger.error(f"Failed to save user message: {e}", exc_info=True)
                yield AgentEvent(
                    event_type=AgentEventType.ERROR,
                    error=f"Failed to save user message: {str(e)}"
                )
                return
        
        # 获取历史消息
        try:
            context_messages = self.build_context_messages(db, session_id)
            
            # 获取会话信息
            session = self.get_session(db, session_id)
            system_prompt = session.system_prompt if session else None
        except Exception as e:
            logger.error(f"Failed to build context: {e}", exc_info=True)
            yield AgentEvent(
                event_type=AgentEventType.ERROR,
                error=f"Failed to build context: {str(e)}"
            )
            return
        
        # 收集完整回复用于保存
        full_answer = ""
        skills_used = []
        events_to_save = []
        
        # 执行 Agent
        try:
            # context_messages 包含了最新的用户消息（因为前面已经保存了）
            # 但 agent_engine.execute_stream 会自动将 user_message 添加到 context
            # 我们必须安全地处理这部分，避免丢失上一条消息或重复当前消息
            
            history_messages = list(context_messages)
            # 安全检查：只有当最后一条确实是当前消息时才移除
            if history_messages and \
               history_messages[-1].get('role') == 'user' and \
               history_messages[-1].get('content') == request.message:
                history_messages.pop()
            
            logger.debug(f"Session {session_id} - Context len: {len(context_messages)} -> History len: {len(history_messages)}")
            
            async for event in self._engine.execute_stream(
                session_id=session_id,
                user_message=request.message,
                messages=history_messages,
                system_prompt=system_prompt,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            ):
                yield event
                
                # 收集回答内容
                if event.event_type == AgentEventType.ANSWER:
                    full_answer += event.content or ""
                
                # 收集使用的技能
                if event.event_type == AgentEventType.SKILL_CALL and event.skill_name:
                    if event.skill_name not in skills_used:
                        skills_used.append(event.skill_name)
                
                events_to_save.append(event)
        except Exception as e:
            logger.error(f"Agent execution error in service: {e}", exc_info=True)
            yield AgentEvent(
                event_type=AgentEventType.ERROR,
                error=f"Agent execution error: {str(e)}"
            )
            return

        # 保存 assistant 消息到数据库
        if full_answer:
            try:
                # 构建 extra_data 包含 agent 步骤信息
                extra_data = None
                if events_to_save:
                    agent_steps = []
                    for event in events_to_save:
                        if event.event_type == AgentEventType.THINKING:
                            agent_steps.append({
                                "type": "thinking",
                                "content": event.content,
                                "timestamp": event.timestamp
                            })
                        elif event.event_type == AgentEventType.SKILL_CALL:
                            agent_steps.append({
                                "type": "skill_call",
                                "skillName": event.skill_name,
                                "content": event.content,
                                "code": event.code,
                                "timestamp": event.timestamp
                            })
                        elif event.event_type == AgentEventType.CODE_EXECUTE:
                            agent_steps.append({
                                "type": "code_execute",
                                "skillName": event.skill_name,
                                "code": event.code,
                                "timestamp": event.timestamp
                            })
                        elif event.event_type == AgentEventType.CODE_RESULT:
                            agent_steps.append({
                                "type": "code_result",
                                "skillName": event.skill_name,
                                "result": event.result,
                                "timestamp": event.timestamp
                            })
                        elif event.event_type == AgentEventType.ANSWER:
                            # 最终回答作为 text 步骤
                            if agent_steps and agent_steps[-1].get("type") == "text":
                                agent_steps[-1]["content"] = (agent_steps[-1].get("content") or "") + (event.content or "")
                            else:
                                agent_steps.append({
                                    "type": "text",
                                    "content": event.content,
                                    "timestamp": event.timestamp
                                })
                    
                    if agent_steps:
                        extra_data = {"agentSteps": agent_steps}
                
                self.add_message(
                    db=db,
                    session_id=session_id,
                    role="assistant",
                    content=full_answer,
                    extra_data=extra_data
                )
                logger.info(f"Saved assistant message for session {session_id}, length={len(full_answer)}")
            except Exception as e:
                logger.error(f"Failed to save assistant message: {e}", exc_info=True)
                # 不中断流程，继续执行

        # 如果是新会话且有回答，异步生成标题
        if request.session_id is None and full_answer:
            try:
                import asyncio
                asyncio.create_task(self._generate_session_title(db, session_id))
            except Exception as e:
                logger.error(f"Failed to schedule title generation: {e}")

    async def _generate_session_title(
        self,
        db: DBSession,
        session_id: str
    ) -> None:
        """异步生成会话标题"""
        try:
            messages = self.get_session_messages(db, session_id, limit=2)
            if not messages:
                return
            
            # 找到最后一条用户消息
            user_message = next(
                (m.content for m in messages if m.role == "user"),
                None
            )
            if not user_message:
                return
            
            # 生成标题
            prompt = f"请为以下对话生成一个简短的标题（不超过20个字），不要使用Markdown格式，直接返回文本：\n\n{user_message[:200]}"
            response = await self.llm.async_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.7
            )
            
            if response.choices:
                title = response.choices[0].message.content.strip()
                # 更彻底地清理 Markdown 和各种格式符号
                # 移除 Markdown 标题标记 (#)
                title = re.sub(r'^#+\s*', '', title)
                # 移除粗体/斜体标记 (**, *, __, _)
                title = re.sub(r'\*{1,2}|_{1,2}', '', title)
                # 移除代码块标记 (```, `)
                title = re.sub(r'`+', '', title)
                # 移除链接格式 [text](url)
                title = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', title)
                # 移除其他常见符号和多余空格
                title = re.sub(r'[\[\]<>|~#]', '', title)
                title = re.sub(r'\s+', ' ', title).strip()
                # 移除首尾引号
                title = title.strip('"\'` ')
                title = title[:50]
                
                self.update_session(
                    db, session_id,
                    SessionUpdate(title=title)
                )
                logger.info(f"Generated title for session {session_id}: {title}")
                
        except Exception as e:
            logger.error(f"Failed to generate session title: {e}")

    # ==================== Memory Management ====================

    def set_memory(
        self,
        db: DBSession,
        session_id: str,
        data: MemoryCreate
    ) -> MemoryResponse:
        """设置会话记忆"""
        from ..database import AgentMemory
        
        # 先更新内存中的记忆
        memory_item = self._context_manager.set_memory(
            session_id=session_id,
            key=data.key,
            value=data.value,
            memory_type=data.memory_type,
            ttl=data.ttl
        )
        
        # 持久化到数据库
        existing = db.query(AgentMemory).filter(
            AgentMemory.session_id == session_id,
            AgentMemory.key == data.key
        ).first()
        
        if existing:
            existing.value = json.dumps(data.value) if isinstance(data.value, (dict, list)) else str(data.value)
            existing.memory_type = data.memory_type
            existing.updated_at = datetime.now(timezone.utc)
            existing.expires_at = memory_item.expires_at
            db.commit()
            db.refresh(existing)
            memory = existing
        else:
            memory = AgentMemory(
                id=str(uuid.uuid4()),
                session_id=session_id,
                key=data.key,
                value=json.dumps(data.value) if isinstance(data.value, (dict, list)) else str(data.value),
                memory_type=data.memory_type,
                expires_at=memory_item.expires_at
            )
            db.add(memory)
            db.commit()
            db.refresh(memory)
        
        return MemoryResponse(
            id=str(memory.id),
            session_id=str(memory.session_id),
            key=memory.key,
            value=data.value,
            memory_type=memory.memory_type,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            expires_at=memory.expires_at
        )

    def get_session_memories(
        self,
        db: DBSession,
        session_id: str
    ) -> List[MemoryResponse]:
        """获取会话记忆"""
        from ..database import AgentMemory
        
        memories = db.query(AgentMemory).filter(
            AgentMemory.session_id == session_id
        ).all()
        
        result = []
        for m in memories:
            try:
                value = json.loads(m.value)
            except (json.JSONDecodeError, TypeError):
                value = m.value
            
            result.append(MemoryResponse(
                id=str(m.id),
                session_id=str(m.session_id),
                key=m.key,
                value=value,
                memory_type=m.memory_type,
                created_at=m.created_at,
                updated_at=m.updated_at,
                expires_at=m.expires_at
            ))
        
        return result

    # ==================== Skills ====================

    def list_skills(self) -> List[Dict[str, str]]:
        """列出所有可用技能"""
        skills = self._skill_registry.list_skills()
        return [s.to_dict() for s in skills]

    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """获取技能内容"""
        return self._skill_registry.get_skill_content(skill_name)

    def refresh_skills(self) -> int:
        """刷新技能列表"""
        self._skill_registry.refresh()
        return len(self._skill_registry.list_skills())


# 全局 Agent 服务实例
agent_service = AgentService()
