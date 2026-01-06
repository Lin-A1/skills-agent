"""
Chat 相关的 ORM 模型
存储聊天会话和消息历史
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .base import Base


class ChatSession(Base):
    """
    聊天会话模型
    存储会话元数据和配置
    """
    __tablename__ = "chat_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True, comment="会话标题")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 会话配置
    model = Column(String(100), nullable=False, comment="使用的模型名称")
    system_prompt = Column(Text, nullable=True, comment="系统提示词")
    temperature = Column(String(10), default="0.7", comment="温度参数")
    max_tokens = Column(Integer, default=2048, comment="最大输出tokens")
    top_p = Column(String(10), default="0.9", comment="Top-P参数")
    
    # 会话状态
    is_active = Column(Boolean, default=True, comment="是否激活")
    is_archived = Column(Boolean, default=False, comment="是否已归档")
    
    # 用户标识（可选，用于多用户场景）
    user_id = Column(String(100), nullable=True, index=True, comment="用户ID")
    
    # 额外数据
    extra_data = Column(JSON, nullable=True, comment="额外元数据")
    
    # 关联消息
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")
    
    # 索引
    __table_args__ = (
        Index("ix_chat_sessions_user_updated", "user_id", "updated_at"),
        Index("ix_chat_sessions_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<ChatSession(id={self.id}, title={self.title})>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "temperature": float(self.temperature) if self.temperature else 0.7,
            "max_tokens": self.max_tokens,
            "top_p": float(self.top_p) if self.top_p else 0.9,
            "is_active": self.is_active,
            "is_archived": self.is_archived,
            "user_id": self.user_id,
            "extra_data": self.extra_data,
            "message_count": len(self.messages) if self.messages else 0
        }


class ChatMessage(Base):
    """
    聊天消息模型
    存储完整的消息历史，支持上下文管理
    """
    __tablename__ = "chat_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 消息内容
    role = Column(String(20), nullable=False, comment="角色: system/user/assistant")
    content = Column(Text, nullable=False, comment="消息内容")
    
    # 消息元数据
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    # Token统计
    prompt_tokens = Column(Integer, nullable=True, comment="输入tokens数")
    completion_tokens = Column(Integer, nullable=True, comment="输出tokens数")
    total_tokens = Column(Integer, nullable=True, comment="总tokens数")
    
    # 模型信息
    model = Column(String(100), nullable=True, comment="使用的模型")
    finish_reason = Column(String(50), nullable=True, comment="完成原因")
    
    # 额外数据（如工具调用、函数调用等）
    extra_data = Column(JSON, nullable=True, comment="额外元数据")
    
    # 关联会话
    session = relationship("ChatSession", back_populates="messages")
    
    # 索引
    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )
    
    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role={self.role})>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "finish_reason": self.finish_reason,
            "extra_data": self.extra_data
        }
    
    def to_openai_format(self):
        """转换为OpenAI消息格式"""
        return {
            "role": self.role,
            "content": self.content
        }
