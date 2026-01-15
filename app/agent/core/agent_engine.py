"""
Agent Engine - Core execution engine for the Agent

核心职责：
1. 解析 LLM 输出中的 skill 调用指令
2. 执行 skill 代码并收集结果
3. 支持一次回答中多次调用 skill
4. 管理执行流程（思考 -> 调用 -> 分析 -> 回答）
5. 生成流式事件输出

设计特点：
- 参考 Claude Code 的 agentic 模式
- 支持中途多次 skill 调用
- 通过 sandbox 执行，不依赖 skill 环境
"""
import logging
import re
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, AsyncGenerator, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ..config import settings
from ..schemas import AgentEvent, AgentEventType
from .skill_registry import get_skill_registry
from .skill_executor import get_skill_executor
from .context_manager import get_context_manager

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent 状态"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    ANSWERING = "answering"
    DONE = "done"
    ERROR = "error"


@dataclass
class ExecutionContext:
    """执行上下文"""
    session_id: str
    user_message: str
    messages: List[Dict[str, str]] = field(default_factory=list)
    skills_used: List[str] = field(default_factory=list)
    execution_results: List[Dict[str, Any]] = field(default_factory=list)
    events: List[AgentEvent] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 10
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    start_time: float = field(default_factory=time.time)


class AgentEngine:
    """
    Agent 执行引擎
    
    负责解析和执行 Agent 的技能调用，支持多轮迭代。
    """
    
    # Skill 调用指令的正则模式
    SKILL_CALL_PATTERN = re.compile(
        r'<execute_skill>\s*'
        r'<skill_name>(.*?)</skill(?:_name)?>\s*'
        r'<code>(.*?)</code>\s*'
        r'</execute_skill>',
        re.DOTALL
    )
    
    # 读取 SKILL.md 的指令模式
    READ_SKILL_PATTERN = re.compile(
        r'<read_skill>\s*(.*?)\s*</read_skill>',
        re.DOTALL
    )
    
    def __init__(self, llm_service=None):
        """
        初始化 Agent 引擎
        
        Args:
            llm_service: LLM 服务实例
        """
        self._llm = llm_service
        self._executor = get_skill_executor()
        self._context_manager = get_context_manager()
        self._skill_registry = get_skill_registry()
        
        logger.info("AgentEngine initialized")
    
    def set_llm_service(self, llm_service) -> None:
        """设置 LLM 服务"""
        self._llm = llm_service
    
    def _emit_event(
        self,
        event_type: AgentEventType,
        content: Optional[str] = None,
        skill_name: Optional[str] = None,
        code: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> AgentEvent:
        """创建事件"""
        return AgentEvent(
            event_type=event_type,
            content=content,
            skill_name=skill_name,
            code=code,
            result=result,
            error=error,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    
    def _parse_skill_calls(self, text: str) -> List[Tuple[str, str]]:
        """
        解析文本中的 skill 调用指令
        
        Args:
            text: LLM 输出文本
            
        Returns:
            [(skill_name, code), ...] 列表
        """
        matches = self.SKILL_CALL_PATTERN.findall(text)
        return [(name.strip(), code.strip()) for name, code in matches]
    
    def _parse_read_skill_requests(self, text: str) -> List[str]:
        """
        解析文本中的读取 skill 请求
        
        Args:
            text: LLM 输出文本
            
        Returns:
            skill 名称列表
        """
        matches = self.READ_SKILL_PATTERN.findall(text)
        return [name.strip() for name in matches]
    
    def _has_pending_actions(self, text: str) -> bool:
        """检查是否有待执行的动作"""
        return bool(
            self.SKILL_CALL_PATTERN.search(text) or
            self.READ_SKILL_PATTERN.search(text)
        )
    
    def _build_execution_prompt(
        self,
        context: ExecutionContext,
        skill_results: List[Dict[str, Any]]
    ) -> str:
        """
        构建包含执行结果的后续提示
        """
        if not skill_results:
            return ""
        
        result_lines = ["以下是技能执行的结果：\n"]
        for i, result in enumerate(skill_results, 1):
            skill_name = result.get("skill_name", "unknown")
            success = result.get("success", False)
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            
            result_lines.append(f"### 执行 {i}: {skill_name}")
            result_lines.append(f"- 状态: {'成功' if success else '失败'}")
            if stdout:
                result_lines.append(f"- 标准输出:\n```\n{stdout[:2000]}\n```")
            if stderr and not success:
                result_lines.append(f"- 错误输出:\n```\n{stderr[:1000]}\n```")
            result_lines.append("")
        
        result_lines.append("\n请根据执行结果继续分析。如果需要进一步操作，可以再次调用技能；如果已获得足够信息，请直接给出最终回答。")
        
        return "\n".join(result_lines)
    
    def _build_skill_content_prompt(self, skill_names: List[str]) -> str:
        """构建 skill 内容提示"""
        contents = []
        for name in skill_names:
            content = self._skill_registry.get_skill_content(name)
            if content:
                contents.append(f"## {name} SKILL.md\n\n{content}")
        
        if contents:
            return "以下是你请求的技能文档：\n\n" + "\n\n---\n\n".join(contents)
        return ""
    
    async def execute_stream(
        self,
        session_id: str,
        user_message: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_iterations: Optional[int] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        流式执行 Agent（主要入口）
        
        这是核心执行方法，支持：
        1. 多轮 skill 调用
        2. 中途继续对话
        3. 流式输出事件
        
        Args:
            session_id: 会话ID
            user_message: 用户消息
            messages: 历史消息列表
            system_prompt: 系统提示词
            model: 模型名称
            temperature: 温度
            max_tokens: 最大 token
            max_iterations: 最大迭代次数
            
        Yields:
            AgentEvent 事件流
        """
        if self._llm is None:
            yield self._emit_event(
                AgentEventType.ERROR,
                error="LLM service not configured"
            )
            return
        
        # 初始化执行上下文
        context = ExecutionContext(
            session_id=session_id,
            user_message=user_message,
            messages=list(messages),
            max_iterations=max_iterations or settings.MAX_ITERATIONS
        )
        
        # 构建系统提示词
        if system_prompt is None:
            system_prompt = self._context_manager.build_system_prompt(
                session_id=session_id,
                include_skills=True,
                include_memory=True
            )
        
        # LLM 参数
        model = model or settings.AGENT_LLM_MODEL_NAME
        temperature = temperature if temperature is not None else settings.DEFAULT_TEMPERATURE
        max_tokens = max_tokens or settings.DEFAULT_MAX_TOKENS
        
        # 构建初始上下文
        context_messages = self._context_manager.build_context_messages(
            messages=context.messages + [{"role": "user", "content": user_message}],
            system_prompt=system_prompt
        )
        
        logger.info(f"Starting agent execution for session {session_id}")
        
        try:
            while context.iteration < context.max_iterations:
                context.iteration += 1
                logger.debug(f"Agent iteration {context.iteration}/{context.max_iterations}")
                
                # 发送思考事件
                yield self._emit_event(
                    AgentEventType.THINKING,
                    content=f"正在分析... (第 {context.iteration} 轮)"
                )
                
                # 调用 LLM，收集完整响应的同时进行流式处理
                full_response = ""
                # Streaming State
                stream_buffer = "" 
                is_streaming_skill = False
                
                async for chunk in self._llm.async_stream_chat_completion(
                    messages=context_messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens
                ):
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            content = delta.content
                            full_response += content
                            
                            # --- Streaming Logic ---
                            # 检测是否进入 Skill Tag
                            # 简单启发式：如果遇到 <ex 或 <re，则进入潜在的 Skill 模式
                            
                            if not is_streaming_skill:
                                if "<" in content or stream_buffer:
                                    stream_buffer += content
                                    
                                    # 检查是否触发 Skill Block
                                    if "<execute_skill" in stream_buffer or "<read_skill" in stream_buffer:
                                        is_streaming_skill = True
                                        # 不要 flush stream_buffer，因为它是代码
                                    elif len(stream_buffer) > 20 and "<" not in stream_buffer:
                                        # 缓冲过长且没有 <，说明之前的 < 只是普通字符
                                        yield self._emit_event(AgentEventType.ANSWER, content=stream_buffer)
                                        stream_buffer = ""
                                    elif stream_buffer.endswith(">"):
                                        # 标签闭合但不是 skill tag (e.g. <br>)
                                        # 简单起见，如果不是目标 tag，就释放
                                        if not (stream_buffer.strip().startswith("<execute_skill") or stream_buffer.strip().startswith("<read_skill")):
                                             yield self._emit_event(AgentEventType.ANSWER, content=stream_buffer)
                                             stream_buffer = ""
                                    # else: 继续缓冲等待
                                else:
                                    # 安全内容，直接流式输出
                                    yield self._emit_event(AgentEventType.ANSWER, content=content)
                            else:
                                # 正在流式传输 Skill，缓冲所有内容直到 Tag 结束
                                stream_buffer += content
                                if "</execute_skill>" in stream_buffer or "</read_skill>" in stream_buffer:
                                    is_streaming_skill = False
                                    stream_buffer = "" # 丢弃代码块文本，稍后会有专门的 SKILL_EXECUTE 事件
                            # --- End Streaming Logic ---

                # Flush remaining buffer if safe
                if stream_buffer and not is_streaming_skill:
                     yield self._emit_event(AgentEventType.ANSWER, content=stream_buffer)
                
                # 检查是否有 skill 调用
                skill_calls = self._parse_skill_calls(full_response)
                read_requests = self._parse_read_skill_requests(full_response)
                
                # 处理读取 skill 请求
                if read_requests:
                    for skill_name in read_requests:
                        yield self._emit_event(
                            AgentEventType.SKILL_CALL,
                            content=f"读取技能文档: {skill_name}",
                            skill_name=skill_name
                        )
                    
                    # 获取 skill 内容并添加到上下文
                    skill_content = self._build_skill_content_prompt(read_requests)
                    if skill_content:
                        context_messages.append({
                            "role": "assistant",
                            "content": full_response
                        })
                        context_messages.append({
                            "role": "user",
                            "content": skill_content
                        })
                        continue
                
                # 处理 skill 调用
                if skill_calls:
                    execution_results = []
                    
                    for skill_name, code in skill_calls:
                        # 发送 skill 调用事件
                        yield self._emit_event(
                            AgentEventType.SKILL_CALL,
                            content=f"正在调用技能: {skill_name}",
                            skill_name=skill_name,
                            code=code
                        )
                        
                        # 发送代码执行事件
                        yield self._emit_event(
                            AgentEventType.CODE_EXECUTE,
                            code=code,
                            skill_name=skill_name
                        )
                        
                        # 执行代码
                        result = self._executor.execute_skill(
                            skill_name=skill_name,
                            code=code
                        )
                        
                        execution_results.append(result)
                        context.execution_results.append(result)
                        
                        if skill_name not in context.skills_used:
                            context.skills_used.append(skill_name)
                        
                        # 发送执行结果事件
                        yield self._emit_event(
                            AgentEventType.CODE_RESULT,
                            skill_name=skill_name,
                            result=result
                        )
                    
                    # 将结果添加到上下文，继续对话
                    result_prompt = self._build_execution_prompt(context, execution_results)
                    context_messages.append({
                        "role": "assistant",
                        "content": full_response
                    })
                    context_messages.append({
                        "role": "user",
                        "content": result_prompt
                    })
                    
                    continue
                
                # 如果没有 skill 调用，且我们已经流式输出了内容，就不需要再发 ANSWER 了。
                # 之前的逻辑是 clean_response 并发送。现在我们假设流式已经发了 clean content。
                pass
                
                # 没有更多动作，完成
                break
            
            # 完成事件
            yield self._emit_event(
                AgentEventType.DONE,
                content="执行完成",
                result={
                    "iterations": context.iteration,
                    "skills_used": context.skills_used,
                    "execution_time": time.time() - context.start_time
                }
            )
            
        except Exception as e:
            logger.error(f"Agent execution error: {e}", exc_info=True)
            yield self._emit_event(
                AgentEventType.ERROR,
                error=str(e)
            )
    
    async def execute(
        self,
        session_id: str,
        user_message: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Tuple[str, List[AgentEvent], List[str]]:
        """
        非流式执行 Agent
        
        Args:
            session_id: 会话ID
            user_message: 用户消息
            messages: 历史消息
            system_prompt: 系统提示词
            model: 模型名称
            temperature: 温度
            max_tokens: 最大 token
            
        Returns:
            (最终回答, 事件列表, 使用的技能列表)
        """
        events = []
        final_content = ""
        skills_used = []
        
        async for event in self.execute_stream(
            session_id=session_id,
            user_message=user_message,
            messages=messages,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        ):
            events.append(event)
            
            if event.event_type == AgentEventType.ANSWER:
                final_content += event.content or ""
            elif event.event_type == AgentEventType.DONE:
                if event.result and "skills_used" in event.result:
                    skills_used = event.result["skills_used"]
        
        return final_content, events, skills_used


# 全局 Agent 引擎实例
_agent_engine: Optional[AgentEngine] = None


def get_agent_engine() -> AgentEngine:
    """获取全局 Agent 引擎实例（单例）"""
    global _agent_engine
    if _agent_engine is None:
        _agent_engine = AgentEngine()
    return _agent_engine
