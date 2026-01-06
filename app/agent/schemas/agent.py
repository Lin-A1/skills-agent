"""
Agent Schemas - Pydantic Models
Request/Response models for Agent API
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field
from uuid import uuid4


class MessageRole(str, Enum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class AgentEventType(str, Enum):
    """Agent 事件类型"""
    # 流程事件
    INTENT = "intent"           # 意图识别结果
    THOUGHT = "thought"         # 思考过程
    ACTION = "action"           # 决定执行的动作
    OBSERVATION = "observation" # 工具执行结果
    FINAL_ANSWER = "final_answer"  # 最终答案
    
    # 状态事件
    START = "start"             # 任务开始
    ITERATION = "iteration"     # 新一轮迭代开始
    COMPLETE = "complete"       # 任务完成
    ERROR = "error"             # 错误
    
    # 内容事件
    TOKEN = "token"             # 流式 token
    TOOL_CALL = "tool_call"     # 工具调用详情
    MEMORY_UPDATE = "memory_update"  # 记忆更新


class ToolAction(BaseModel):
    """工具调用动作"""
    tool_name: str = Field(..., description="工具名称")
    method: str = Field(default="execute", description="调用方法")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="调用参数")
    
    # 执行结果（填充后）
    success: Optional[bool] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None


class StepResult(BaseModel):
    """单步执行结果"""
    step_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    type: AgentEventType
    content: Any
    tool_action: Optional[ToolAction] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    iteration: int = 0
    
    class Config:
        use_enum_values = True


class AgentEvent(BaseModel):
    """Agent SSE 事件"""
    event_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    type: AgentEventType
    data: Any
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # 可选的元数据
    iteration: Optional[int] = None
    tool_name: Optional[str] = None
    execution_time: Optional[float] = None
    
    class Config:
        use_enum_values = True


class AgentRequest(BaseModel):
    """Agent 执行请求"""
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话ID，不提供则创建新会话")
    user_id: Optional[str] = Field(None, description="用户ID")
    
    # 图片输入（多模态）
    images: Optional[List[str]] = Field(
        None, 
        description="图片列表（URL 或本地路径或 base64 数据）"
    )
    
    # 执行参数
    stream: bool = Field(True, description="是否流式返回")
    max_iterations: int = Field(10, ge=1, le=50, description="最大迭代次数")
    
    # LLM 参数
    model: Optional[str] = Field(None, description="模型名称")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(None, ge=1, description="最大输出 tokens")
    
    # 可选的上下文
    system_prompt: Optional[str] = Field(None, description="自定义系统提示词")
    context: Optional[Dict[str, Any]] = Field(None, description="额外上下文信息")
    
    # 工具控制
    enabled_tools: Optional[List[str]] = Field(None, description="启用的工具列表，None 表示全部启用")
    disabled_tools: Optional[List[str]] = Field(None, description="禁用的工具列表")


class AgentResponse(BaseModel):
    """Agent 非流式响应"""
    session_id: str
    message_id: str
    
    # 结果
    answer: str = Field(..., description="最终答案")
    
    # 执行过程摘要
    iterations: int = Field(..., description="实际迭代次数")
    tools_used: List[str] = Field(default_factory=list, description="使用的工具列表")
    
    # 时间信息
    started_at: datetime
    completed_at: datetime
    total_time: float = Field(..., description="总耗时（秒）")
    
    # Token 统计
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ToolInfo(BaseModel):
    """工具信息"""
    name: str
    description: str
    available: bool = True
    methods: List[str] = Field(default_factory=list)


class AgentStatus(BaseModel):
    """Agent 状态"""
    status: Literal["healthy", "degraded", "unhealthy"]
    service: str = "agent"
    version: str = "0.1.0"
    available_tools: List[ToolInfo] = Field(default_factory=list)
    active_sessions: Optional[int] = None
