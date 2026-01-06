"""
Agent 相关的 ORM 模型
存储 Agent 会话和消息历史
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .base import Base


class AgentSession(Base):
    """
    Agent 会话模型
    存储 Agent 会话元数据和配置
    """
    __tablename__ = "agent_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, index=True, comment="用户ID")
    title = Column(String(255), nullable=True, comment="会话标题")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 会话状态
    is_active = Column(Boolean, default=True, comment="是否激活")
    is_archived = Column(Boolean, default=False, comment="是否已归档")
    
    # 会话统计
    message_count = Column(Integer, default=0, comment="消息数量")
    total_tokens = Column(Integer, default=0, comment="总 token 数")
    
    # 会话上下文（临时性的会话级数据）
    session_context = Column(JSON, nullable=True, comment="会话级别上下文")
    
    # 额外元数据
    extra_data = Column(JSON, nullable=True, comment="额外元数据")
    
    # 关联消息
    messages = relationship(
        "AgentMessage", 
        back_populates="session", 
        cascade="all, delete-orphan", 
        order_by="AgentMessage.created_at"
    )
    
    # 索引
    __table_args__ = (
        Index("ix_agent_sessions_user_updated", "user_id", "updated_at"),
        Index("ix_agent_sessions_user_active", "user_id", "is_active"),
    )
    
    def __repr__(self):
        return f"<AgentSession(id={self.id}, user_id={self.user_id})>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active,
            "is_archived": self.is_archived,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
            "session_context": self.session_context,
            "extra_data": self.extra_data,
        }


class AgentMessage(Base):
    """
    Agent 消息模型
    存储 Agent 对话的完整消息历史
    """
    __tablename__ = "agent_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # 消息内容
    role = Column(String(20), nullable=False, comment="角色: user/assistant/tool/system")
    content = Column(Text, nullable=False, comment="消息内容")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    # Token 统计
    tokens = Column(Integer, nullable=True, comment="消息 token 数")
    
    # 工具相关
    tool_name = Column(String(100), nullable=True, comment="工具名称（如果是工具消息）")
    tool_result = Column(JSON, nullable=True, comment="工具执行结果")
    
    # 额外元数据
    extra_data = Column(JSON, nullable=True, comment="额外元数据")
    
    # 关联会话
    session = relationship("AgentSession", back_populates="messages")
    
    # 索引
    __table_args__ = (
        Index("ix_agent_messages_session_created", "session_id", "created_at"),
    )
    
    def __repr__(self):
        return f"<AgentMessage(id={self.id}, role={self.role})>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tokens": self.tokens,
            "tool_name": self.tool_name,
            "tool_result": self.tool_result,
            "extra_data": self.extra_data,
        }
    
    def to_openai_format(self):
        """转换为 OpenAI 消息格式"""
        # 工具消息转为 assistant
        role = "assistant" if self.role == "tool" else self.role
        return {
            "role": role,
            "content": self.content
        }
