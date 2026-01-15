"""
Pydantic schemas for Agent API
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
    TOOL = "tool"


class AgentEventType(str, Enum):
    """Agent 事件类型"""
    THINKING = "thinking"           # 思考过程
    SKILL_CALL = "skill_call"       # 调用 Skill
    SKILL_RESULT = "skill_result"   # Skill 执行结果
    CODE_EXECUTE = "code_execute"   # 代码执行
    CODE_RESULT = "code_result"     # 代码执行结果
    ANSWER = "answer"               # 最终回答（流式）
    ERROR = "error"                 # 错误
    DONE = "done"                   # 完成


# ============ Skill Schemas ============

class SkillMetadata(BaseModel):
    """Skill 元数据"""
    name: str
    description: str
    path: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "sandbox-service",
                "description": "安全隔离的 Docker 沙盒代码执行服务",
                "path": "/app/services/sandbox_service"
            }
        }


class SkillDetail(BaseModel):
    """Skill 详情（包含完整内容）"""
    name: str
    description: str
    path: str
    content: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "sandbox-service",
                "description": "安全隔离的 Docker 沙盒代码执行服务",
                "path": "/app/services/sandbox_service",
                "content": "---\nname: sandbox-service\n..."
            }
        }


class SkillListResponse(BaseModel):
    """Skill 列表响应"""
    skills: List[SkillMetadata]
    total: int


# ============ Agent Event Schemas ============

class AgentEvent(BaseModel):
    """Agent 事件（用于流式输出）"""
    event_type: AgentEventType
    content: Optional[str] = None
    skill_name: Optional[str] = None
    code: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "thinking",
                "content": "正在分析用户请求...",
                "timestamp": "2026-01-14T20:00:00Z"
            }
        }


# ============ Message Schemas ============

class MessageCreate(BaseModel):
    """创建消息请求"""
    role: MessageRole
    content: str


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    event_type: Optional[str] = None
    skill_name: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
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
    temperature: Optional[float] = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=4096, ge=1, le=32000)
    user_id: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "新的 Agent 对话",
                "system_prompt": "你是一个智能助手，可以调用各种技能完成任务。"
            }
        }


class SessionUpdate(BaseModel):
    """更新会话请求"""
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=32000)
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


# ============ Agent Request/Response Schemas ============

class AgentRequest(BaseModel):
    """Agent 请求"""
    # 会话ID（如果提供则使用现有会话，否则创建新会话）
    session_id: Optional[str] = None
    
    # 用户消息
    message: str = Field(..., min_length=1, description="用户输入的消息")
    
    # 图片列表（base64 编码）
    images: Optional[List[str]] = Field(
        default=None,
        description="Base64 编码的图片列表，将通过 OCR+LLM 分析"
    )
    
    # 模型配置
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=32000)
    
    # 流式输出
    stream: bool = True
    
    # 跳过保存用户消息（用于重新生成场景）
    skip_save_user_message: bool = False
    
    # 用户标识
    user_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "message": "请帮我搜索关于 Python 异步编程的最新资料",
                "stream": True
            }
        }


class UsageInfo(BaseModel):
    """Token 使用信息"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AgentResponse(BaseModel):
    """Agent 非流式响应"""
    id: str
    session_id: str
    model: str
    content: str
    events: List[AgentEvent]
    skills_used: List[str]
    usage: UsageInfo
    created: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "agent-abc123",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "model": "mimo-v2-flash",
                "content": "根据搜索结果，Python 异步编程的最新资料包括...",
                "events": [],
                "skills_used": ["deepsearch-service"],
                "usage": {
                    "prompt_tokens": 500,
                    "completion_tokens": 200,
                    "total_tokens": 700
                },
                "created": 1705276800
            }
        }


# ============ Memory Schemas ============

class MemoryCreate(BaseModel):
    """创建记忆"""
    key: str = Field(..., min_length=1, description="记忆的键名")
    value: Any = Field(..., description="记忆的内容")
    memory_type: str = Field(default="fact", description="记忆类型: fact, preference, context")
    ttl: Optional[int] = Field(default=None, description="过期时间（秒），None表示永不过期")
    
    class Config:
        json_schema_extra = {
            "example": {
                "key": "user_name",
                "value": "张三",
                "memory_type": "fact"
            }
        }


class MemoryResponse(BaseModel):
    """记忆响应"""
    id: str
    session_id: str
    key: str
    value: Any
    memory_type: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None


class MemoryListResponse(BaseModel):
    """记忆列表响应"""
    memories: List[MemoryResponse]
    total: int
