"""
Session Memory - Persistent Conversation Context Management
Handles message history and context for individual Agent sessions with database storage
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session as DBSession

logger = logging.getLogger(__name__)


class SessionMemory:
    """
    会话记忆管理（数据库持久化版本）
    
    维护单个 Agent 会话的消息历史和上下文
    """
    
    def __init__(
        self,
        db_session: DBSession,
        session_id: Optional[str] = None,
        user_id: str = "anonymous",
        max_messages: int = 100,
        max_tokens: int = 16000
    ):
        """
        初始化会话记忆
        
        Args:
            db_session: 数据库会话
            session_id: 会话ID，不提供则自动生成
            user_id: 用户ID
            max_messages: 最大消息数量
            max_tokens: 最大 token 数量
        """
        self.db = db_session
        self.user_id = user_id
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        
        # 导入模型（延迟导入避免循环依赖）
        from storage.pgsql.models import AgentSession, AgentMessage
        self.AgentSession = AgentSession
        self.AgentMessage = AgentMessage
        
        # 加载或创建会话
        if session_id:
            self.session = self._load_session(session_id)
            if not self.session:
                self.session = self._create_session(session_id)
        else:
            self.session = self._create_session()
        
        self.session_id = str(self.session.id)
    
    def _load_session(self, session_id: str) -> Optional[Any]:
        """加载已存在的会话"""
        try:
            session_uuid = UUID(session_id)
            session = self.db.query(self.AgentSession).filter(
                self.AgentSession.id == session_uuid,
                self.AgentSession.is_active == True
            ).first()
            
            if session:
                logger.debug(f"Loaded session {session_id}")
            return session
        except Exception as e:
            logger.warning(f"Failed to load session {session_id}: {e}")
            return None
    
    def _create_session(self, session_id: Optional[str] = None) -> Any:
        """创建新会话"""
        session = self.AgentSession(
            id=UUID(session_id) if session_id else uuid4(),
            user_id=self.user_id,
            is_active=True,
            message_count=0,
            total_tokens=0,
            session_context={}
        )
        self.db.add(session)
        self.db.flush()
        logger.info(f"Created new session {session.id} for user {self.user_id}")
        return session
    
    def add_message(
        self,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        tool_result: Optional[Dict] = None,
        **kwargs
    ) -> str:
        """
        添加消息到会话
        
        Args:
            role: 消息角色 (user/assistant/system/tool)
            content: 消息内容
            tool_name: 工具名称（可选）
            tool_result: 工具结果（可选）
            **kwargs: 额外属性
            
        Returns:
            消息ID
        """
        tokens = self._estimate_tokens(content)
        
        message = self.AgentMessage(
            session_id=self.session.id,
            role=role,
            content=content,
            tokens=tokens,
            tool_name=tool_name,
            tool_result=tool_result,
            extra_data=kwargs if kwargs else None
        )
        
        self.db.add(message)
        
        # 更新会话统计
        self.session.message_count = (self.session.message_count or 0) + 1
        self.session.total_tokens = (self.session.total_tokens or 0) + tokens
        self.session.updated_at = datetime.utcnow()
        
        self.db.flush()
        
        # 执行限制
        self._enforce_limits()
        
        return str(message.id)
    
    def add_user_message(self, content: str, **kwargs) -> str:
        """添加用户消息"""
        return self.add_message("user", content, **kwargs)
    
    def add_assistant_message(self, content: str, **kwargs) -> str:
        """添加助手消息"""
        return self.add_message("assistant", content, **kwargs)
    
    def add_tool_message(
        self,
        tool_name: str,
        tool_result: Any,
        **kwargs
    ) -> str:
        """添加工具调用结果消息"""
        content = f"[Tool: {tool_name}]\n{self._format_tool_result(tool_result)}"
        return self.add_message(
            "tool", 
            content, 
            tool_name=tool_name, 
            tool_result=tool_result if isinstance(tool_result, dict) else {"result": str(tool_result)},
            **kwargs
        )
    
    def _format_tool_result(self, result: Any, max_length: int = 1000) -> str:
        """格式化工具结果"""
        if isinstance(result, dict):
            if result.get("success"):
                if "stdout" in result.get("result", {}):
                    return result["result"]["stdout"][:max_length]
                return str(result.get("result", ""))[:max_length]
            else:
                return f"Error: {result.get('error', 'Unknown error')}"
        return str(result)[:max_length]
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)
    
    def _enforce_limits(self) -> None:
        """强制执行消息限制"""
        # 获取当前消息数量
        message_count = self.db.query(self.AgentMessage).filter(
            self.AgentMessage.session_id == self.session.id
        ).count()
        
        # 如果超过限制，删除最旧的消息
        if message_count > self.max_messages:
            excess_count = message_count - self.max_messages
            oldest_messages = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.session_id == self.session.id
            ).order_by(self.AgentMessage.created_at).limit(excess_count).all()
            
            for msg in oldest_messages:
                self.session.total_tokens = max(0, (self.session.total_tokens or 0) - (msg.tokens or 0))
                self.db.delete(msg)
            
            self.session.message_count = self.max_messages
            self.db.flush()
            logger.debug(f"Removed {excess_count} old messages from session {self.session_id}")
    
    def get_user_message_count(self) -> int:
        """
        获取 user 消息数量（对话轮数）
        
        用于判断是否自动注入上下文：
        - 4 轮以内：自动注入完整历史
        - 超过 4 轮：提示 Agent 使用 memory_service
        """
        return self.db.query(self.AgentMessage).filter(
            self.AgentMessage.session_id == self.session.id,
            self.AgentMessage.role == "user"
        ).count()
    
    def get_messages(
        self,
        limit: Optional[int] = None,
        roles: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        获取消息列表
        
        Args:
            limit: 最大返回数量
            roles: 过滤的角色列表
            
        Returns:
            消息列表
        """
        query = self.db.query(self.AgentMessage).filter(
            self.AgentMessage.session_id == self.session.id
        )
        
        if roles:
            query = query.filter(self.AgentMessage.role.in_(roles))
        
        query = query.order_by(self.AgentMessage.created_at)
        
        if limit:
            # 获取最后 N 条
            total = query.count()
            if total > limit:
                query = query.offset(total - limit)
        
        messages = query.all()
        return [msg.to_dict() for msg in messages]
    
    def get_openai_messages(
        self,
        include_system: bool = True,
        system_prompt: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        获取 OpenAI 格式的消息列表
        
        Args:
            include_system: 是否包含系统消息
            system_prompt: 自定义系统提示词
            limit: 最大消息数量
            
        Returns:
            OpenAI 格式的消息列表
        """
        messages = []
        
        # 添加系统消息
        if include_system and system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        # 获取历史消息
        query = self.db.query(self.AgentMessage).filter(
            self.AgentMessage.session_id == self.session.id
        ).order_by(self.AgentMessage.created_at)
        
        if limit:
            total = query.count()
            if total > limit:
                query = query.offset(total - limit)
        
        for msg in query.all():
            messages.append(msg.to_openai_format())
        
        return messages
    
    def set_context(self, key: str, value: Any) -> None:
        """设置会话级别上下文"""
        if self.session.session_context is None:
            self.session.session_context = {}
        context = dict(self.session.session_context)
        context[key] = value
        self.session.session_context = context
        self.db.flush()
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """获取会话级别上下文"""
        if self.session.session_context is None:
            return default
        return self.session.session_context.get(key, default)
    
    def get_summary(self) -> str:
        """生成会话摘要，包含最近的对话历史"""
        # 获取最近的消息（用户和助手都要）
        recent_messages = self.db.query(self.AgentMessage).filter(
            self.AgentMessage.session_id == self.session.id
        ).order_by(self.AgentMessage.created_at.desc()).limit(6).all()
        
        if not recent_messages:
            return "空会话"
        
        # 反转顺序（从旧到新）
        recent_messages = list(reversed(recent_messages))
        
        # 构建对话历史
        history_parts = []
        for msg in recent_messages:
            role_label = "用户" if msg.role == "user" else "助手"
            content = msg.content if msg.content else "(空)"
            # 跳过占位符消息
            if content == "(No response generated)":
                continue
            history_parts.append(f"【{role_label}】: {content}")
        
        summary = "## 最近对话历史\n" + "\n\n".join(history_parts)
        summary += f"\n\n---\n总消息数: {self.session.message_count or 0}"
        
        return summary
    
    def delete_message(self, message_id: str) -> bool:
        """删除单条消息"""
        try:
            msg = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.id == message_id,
                self.AgentMessage.session_id == self.session.id
            ).first()
            
            if msg:
                self.session.total_tokens = max(0, (self.session.total_tokens or 0) - (msg.tokens or 0))
                self.db.delete(msg)
                self.session.message_count = max(0, (self.session.message_count or 0) - 1)
                self.db.flush()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete message {message_id}: {e}")
            return False

    def delete_messages_after(self, message_id: str, include_target: bool = True) -> int:
        """
        删除指定消息之后的所有消息
        
        Args:
            message_id: 目标消息ID
            include_target: 是否包含目标消息本身
            
        Returns:
            删除的消息数量
        """
        try:
            target_msg = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.id == message_id,
                self.AgentMessage.session_id == self.session.id
            ).first()
            
            if not target_msg:
                return 0
                
            query = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.session_id == self.session.id,
                self.AgentMessage.created_at >= target_msg.created_at
            )
            
            if not include_target:
                query = query.filter(self.AgentMessage.id != message_id)
                
            messages_to_delete = query.all()
            count = len(messages_to_delete)
            
            for msg in messages_to_delete:
                self.session.total_tokens = max(0, (self.session.total_tokens or 0) - (msg.tokens or 0))
                self.db.delete(msg)
            
            self.session.message_count = max(0, (self.session.message_count or 0) - count)
            self.db.flush()
            return count
        except Exception as e:
            logger.error(f"Failed to delete messages after {message_id}: {e}")
            return 0
            
    def clear(self) -> None:
        """清空会话记忆（删除所有消息）"""
        self.db.query(self.AgentMessage).filter(
            self.AgentMessage.session_id == self.session.id
        ).delete()
        
        self.session.message_count = 0
        self.session.total_tokens = 0
        self.session.session_context = {}
        self.session.updated_at = datetime.utcnow()
        self.db.flush()
    
    def archive(self) -> None:
        """归档会话"""
        self.session.is_archived = True
        self.session.is_active = False
        self.session.updated_at = datetime.utcnow()
        self.db.flush()
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "messages": self.get_messages(),
            "session_context": self.session.session_context or {},
            "message_count": self.session.message_count,
            "total_tokens": self.session.total_tokens,
            "created_at": self.session.created_at.isoformat() if self.session.created_at else None,
            "updated_at": self.session.updated_at.isoformat() if self.session.updated_at else None,
        }


class SessionMemoryManager:
    """会话记忆管理器"""
    
    def __init__(self, db_session_factory):
        """
        初始化管理器
        
        Args:
            db_session_factory: 数据库会话工厂函数
        """
        self.db_session_factory = db_session_factory
        self._cache: Dict[str, SessionMemory] = {}
    
    def get(
        self,
        session_id: Optional[str] = None,
        user_id: str = "anonymous",
        create_if_missing: bool = True
    ) -> Optional[SessionMemory]:
        """
        获取或创建会话记忆
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            create_if_missing: 如果不存在是否创建
        """
        cache_key = session_id or f"new_{user_id}_{uuid4()}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        db = self.db_session_factory()
        try:
            memory = SessionMemory(
                db_session=db,
                session_id=session_id,
                user_id=user_id
            )
            self._cache[memory.session_id] = memory
            return memory
        except Exception as e:
            logger.error(f"Failed to get/create session memory: {e}")
            db.rollback()
            if not create_if_missing:
                return None
            raise
    
    def commit(self, session_id: str) -> None:
        """提交会话更改"""
        if session_id in self._cache:
            try:
                self._cache[session_id].db.commit()
            except Exception as e:
                logger.error(f"Failed to commit session {session_id}: {e}")
                self._cache[session_id].db.rollback()
                raise
    
    def close(self, session_id: str) -> None:
        """关闭并移除会话"""
        if session_id in self._cache:
            try:
                self._cache[session_id].db.commit()
                self._cache[session_id].db.close()
            except Exception:
                pass
            del self._cache[session_id]
    
    def clear_cache(self) -> None:
        """清除所有缓存"""
        for session_id in list(self._cache.keys()):
            self.close(session_id)
