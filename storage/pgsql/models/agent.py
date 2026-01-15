"""
Agent 相关的 ORM 模型
存储 Agent 会话、消息和记忆
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON, Boolean, Index, Float
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .base import Base


class AgentSession(Base):
    """
    Agent 会话模型
    存储会话元数据和配置
    """
    __tablename__ = "agent_sessions_v2"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True, comment="会话标题")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 会话配置
    model = Column(String(100), nullable=False, comment="使用的模型名称")
    system_prompt = Column(Text, nullable=True, comment="系统提示词")
    temperature = Column(Float, default=0.3, comment="温度参数")
    max_tokens = Column(Integer, default=4096, comment="最大输出tokens")
    
    # 会话状态
    is_active = Column(Boolean, default=True, comment="是否激活")
    is_archived = Column(Boolean, default=False, comment="是否已归档")
    
    # 用户标识
    user_id = Column(String(100), nullable=True, index=True, comment="用户ID")
    
    # 额外数据
    extra_data = Column(JSON, nullable=True, comment="额外元数据")
    
    # 关联
    messages = relationship("AgentMessage", back_populates="session", cascade="all, delete-orphan", order_by="AgentMessage.created_at")
    memories = relationship("AgentMemory", back_populates="session", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index("ix_agent_sessions_v2_user_updated", "user_id", "updated_at"),
        Index("ix_agent_sessions_v2_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<AgentSession(id={self.id}, title={self.title})>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "is_active": self.is_active,
            "is_archived": self.is_archived,
            "user_id": self.user_id,
            "extra_data": self.extra_data,
            "message_count": len(self.messages) if self.messages else 0
        }


class AgentMessage(Base):
    """
    Agent 消息模型
    存储完整的消息历史，包括技能调用记录
    """
    __tablename__ = "agent_messages_v2"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("agent_sessions_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 消息内容
    role = Column(String(20), nullable=False, comment="角色: system/user/assistant/tool")
    content = Column(Text, nullable=False, comment="消息内容")
    
    # 消息元数据
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    # Agent 特有字段
    event_type = Column(String(50), nullable=True, comment="事件类型: thinking/skill_call/answer等")
    skill_name = Column(String(100), nullable=True, comment="调用的技能名称")
    execution_result = Column(JSON, nullable=True, comment="执行结果")
    
    # 额外数据
    extra_data = Column(JSON, nullable=True, comment="额外元数据")
    
    # 关联会话
    session = relationship("AgentSession", back_populates="messages")
    
    # 索引
    __table_args__ = (
        Index("ix_agent_messages_v2_session_created", "session_id", "created_at"),
        Index("ix_agent_messages_v2_skill", "skill_name"),
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
            "event_type": self.event_type,
            "skill_name": self.skill_name,
            "execution_result": self.execution_result,
            "extra_data": self.extra_data
        }


class AgentMemory(Base):
    """
    Agent 记忆模型
    存储持久化的会话记忆
    """
    __tablename__ = "agent_memories_v2"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("agent_sessions_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 记忆内容
    key = Column(String(255), nullable=False, comment="记忆键名")
    value = Column(Text, nullable=False, comment="记忆值（JSON字符串）")
    memory_type = Column(String(50), default="fact", comment="记忆类型: fact/preference/context")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    expires_at = Column(DateTime, nullable=True, comment="过期时间")
    
    # 关联会话
    session = relationship("AgentSession", back_populates="memories")
    
    # 索引和约束
    __table_args__ = (
        Index("ix_agent_memories_v2_session_key", "session_id", "key", unique=True),
        Index("ix_agent_memories_v2_type", "memory_type"),
        Index("ix_agent_memories_v2_expires", "expires_at"),
    )
    
    def __repr__(self):
        return f"<AgentMemory(id={self.id}, key={self.key})>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "key": self.key,
            "value": self.value,
            "memory_type": self.memory_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
