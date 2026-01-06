"""
Pydantic schemas for Chat API
Compatible with OpenAI API format
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


# ============ Message Schemas ============

class MessageCreate(BaseModel):
    """创建消息请求"""
    role: MessageRole
    content: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "你好，请介绍一下你自己。"
            }
        }


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None


class MessageListResponse(BaseModel):
    """消息列表响应"""
    messages: List[MessageResponse]
    total: int


# ============ Session Schemas ============

class SessionCreate(BaseModel):
    """创建会话请求"""
    title: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=2048, ge=1, le=32000)
    top_p: Optional[float] = Field(default=0.9, ge=0.0, le=1.0)
    user_id: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "新对话",
                "model": "gpt-4",
                "system_prompt": "你是一个有帮助的AI助手。",
                "temperature": 0.7,
                "max_tokens": 2048
            }
        }


class SessionUpdate(BaseModel):
    """更新会话请求"""
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=32000)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None
    is_archived: Optional[bool] = None
    extra_data: Optional[Dict[str, Any]] = None


class SessionResponse(BaseModel):
    """会话响应"""
    id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    model: str
    system_prompt: Optional[str]
    temperature: float
    max_tokens: int
    top_p: float
    is_active: bool
    is_archived: bool
    user_id: Optional[str]
    extra_data: Optional[Dict[str, Any]]
    message_count: int = 0


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionResponse]
    total: int
    page: int
    page_size: int


# ============ Chat Completion Schemas (OpenAI Compatible) ============

class ChatMessage(BaseModel):
    """聊天消息（OpenAI格式）"""
    role: MessageRole
    content: str


class UsageInfo(BaseModel):
    """Token使用信息"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatRequest(BaseModel):
    """
    聊天请求（兼容OpenAI格式）
    """
    # 会话ID（如果提供则使用现有会话，否则创建新会话）
    session_id: Optional[str] = None
    
    # 消息（如果 session_id 为空，可以提供完整消息历史）
    messages: Optional[List[ChatMessage]] = None
    
    # 用户消息（简化形式，只发送一条用户消息）
    message: Optional[str] = None
    
    # 图片列表（base64 编码，用于 OCR+LLM 分析，不存储）
    images: Optional[List[str]] = Field(
        default=None, 
        description="Base64 编码的图片列表，将通过 OCR+LLM 分析后作为上下文"
    )
    
    # 模型配置
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=32000)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    
    # 流式输出
    stream: bool = False
    
    # 跳过保存用户消息（用于重新生成场景）
    skip_save_user_message: bool = False
    
    # 用户标识
    user_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "message": "你好，请介绍一下你自己。",
                "images": ["data:image/png;base64,iVBORw0KGgoAAAA..."],
                "stream": False
            }
        }


class ChatChoice(BaseModel):
    """聊天选项（OpenAI格式）"""
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatResponse(BaseModel):
    """
    聊天响应（兼容OpenAI格式）
    """
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    session_id: str
    choices: List[ChatChoice]
    usage: UsageInfo
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "chatcmpl-abc123",
                "object": "chat.completion",
                "created": 1703980800,
                "model": "gpt-4",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "你好！我是一个AI助手..."
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 50,
                    "total_tokens": 60
                }
            }
        }


class ChatStreamChunk(BaseModel):
    """
    流式聊天响应块（兼容OpenAI格式）
    """
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    session_id: str
    choices: List[Dict[str, Any]]
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "chatcmpl-abc123",
                "object": "chat.completion.chunk",
                "created": 1703980800,
                "model": "gpt-4",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": "你"
                        },
                        "finish_reason": None
                    }
                ]
            }
        }
