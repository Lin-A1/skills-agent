"""
ReAct Engine - Reasoning and Acting Loop
Core reasoning engine implementing the ReAct framework
"""
import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
from datetime import datetime

from ..config import settings
from ..schemas.agent import AgentEvent, AgentEventType, StepResult, ToolAction
from .prompt_templates import (
    AGENT_SYSTEM_PROMPT,
    REACT_STEP_PROMPT,
    FINAL_ANSWER_TEMPLATE,
    ERROR_RECOVERY_PROMPT,
    format_history,
    format_observations,
    format_tool_list
)
from .skill_executor import skill_executor

logger = logging.getLogger(__name__)


class ReActEngine:
    """
    ReAct 推理引擎
    
    实现 Reasoning → Action → Observation 循环
    """
    
    def __init__(
        self,
        llm_service=None,
        max_iterations: int = None,
        temperature: float = None
    ):
        """
        初始化 ReAct 引擎
        
        Args:
            llm_service: LLM 服务实例
            max_iterations: 最大迭代次数
            temperature: LLM 温度参数
        """
        self._llm_service = llm_service
        self.max_iterations = max_iterations or settings.AGENT_MAX_ITERATIONS
        self.temperature = temperature or settings.AGENT_DEFAULT_TEMPERATURE
        self.skill_executor = skill_executor
    
    @property
    def llm_service(self):
        """懒加载 LLM 服务"""
        if self._llm_service is None:
            from ..services.llm_service import agent_llm_service
            self._llm_service = agent_llm_service
        return self._llm_service
    
    def _inject_context_params(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        为特定工具自动注入上下文参数
        
        目前支持：
        - memory_service: 自动注入 session_id（限制在当前会话内搜索）
        """
        if tool_name == "memory_service":
            # 自动注入 session_id
            if "session_id" not in arguments and hasattr(self, '_current_context'):
                session_id = self._current_context.get("session_id")
                if session_id:
                    arguments = {**arguments, "session_id": session_id}
                    logger.debug(f"Auto-injected session_id for memory_service: {session_id}")
        
        return arguments
    
    async def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        enabled_tools: Optional[List[str]] = None,
        disabled_tools: Optional[List[str]] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        执行 ReAct 循环
        
        Args:
            task: 用户任务/问题
            context: 可选的上下文信息（知识空间、历史等）
            enabled_tools: 启用的工具列表
            disabled_tools: 禁用的工具列表
            
        Yields:
            AgentEvent 事件流
        """
        start_time = time.time()
        history: List[Dict[str, Any]] = []
        observations: List[Dict[str, Any]] = []
        
        # 保存当前上下文，供工具执行时使用
        self._current_context = context or {}
        
        # 发送开始事件
        yield AgentEvent(
            type=AgentEventType.START,
            data={"task": task, "max_iterations": self.max_iterations}
        )
        
        # 构建系统提示词
        available_tools = self._get_available_tools(enabled_tools, disabled_tools)
        system_prompt = self._build_system_prompt(available_tools, context)
        
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"ReAct iteration {iteration}/{self.max_iterations}")
            
            # 发送迭代开始事件
            yield AgentEvent(
                type=AgentEventType.ITERATION,
                data={"iteration": iteration},
                iteration=iteration
            )
            
            try:
                # 1. 思考阶段：调用 LLM 进行推理
                step_result = await self._think(task, history, system_prompt)
                
                # 发送思考事件
                yield AgentEvent(
                    type=AgentEventType.THOUGHT,
                    data=step_result.get("thought", ""),
                    iteration=iteration
                )
                
                # 2. 检查是否有最终答案
                if "final_answer" in step_result:
                    yield AgentEvent(
                        type=AgentEventType.FINAL_ANSWER,
                        data=step_result["final_answer"],
                        iteration=iteration,
                        execution_time=time.time() - start_time
                    )
                    
                    # 发送完成事件
                    yield AgentEvent(
                        type=AgentEventType.COMPLETE,
                        data={
                            "iterations": iteration,
                            "total_time": time.time() - start_time,
                            "tools_used": [obs["tool"] for obs in observations]
                        }
                    )
                    return
                
                # 3. 行动阶段：执行工具调用（支持单个或并行）
                actions_to_execute = []
                
                # 支持单个 action
                if step_result.get("action"):
                    actions_to_execute = [step_result["action"]]
                # 支持并行 actions 数组
                elif step_result.get("actions"):
                    actions_to_execute = step_result["actions"]
                
                # 过滤无效的动作
                actions_to_execute = [a for a in actions_to_execute if isinstance(a, dict)]
                
                if actions_to_execute:
                    # Check for duplicate actions to prevent infinite loops
                    unique_actions = []
                    duplicate_observations = []
                    
                    for action in actions_to_execute:
                        if self._is_duplicate_action(action, history):
                            logger.warning(f"Duplicate action detected: {action}")
                            # Create a fake observation for the duplicate action
                            dup_obs = {
                                "success": False,
                                "error": "SYSTEM WARNING: You have already executed this exact action in this session. Please modify your query or strategy significantly.",
                                "result": None
                            }
                            # Dispatch observation event immediately
                            yield AgentEvent(
                                type=AgentEventType.OBSERVATION,
                                data=dup_obs,
                                iteration=iteration,
                                tool_name=action.get("tool"),
                                execution_time=0
                            )
                            
                            # Add to tracking
                            duplicate_observations.append({
                                "tool": action.get("tool"),
                                "action": action,
                                "result": dup_obs
                            })
                            
                            # Add to global observations list if needed for final answer
                            observations.append({
                                "tool": action.get("tool"),
                                "result": dup_obs["error"]
                            })
                        else:
                            unique_actions.append(action)
                    
                    # Update actions to execute only unique ones
                    actions_to_execute = unique_actions
                    
                    # If we filtered out actions, we need to update history with the duplicate observations
                    if duplicate_observations:
                        if not actions_to_execute:
                            # All actions were duplicates, append history and continue to next iteration
                            history.append({
                                "thought": step_result.get("thought"),
                                "actions": [], # No real actions executed
                                "observations": [item["result"] for item in duplicate_observations] # But we have observations
                            })
                            continue
                        else:
                            # Mixed case: some duplicates, some unique. 
                            # We'll attach duplicate observations to the history entry created after unique execution
                            pass 

                if actions_to_execute:

                    # 并行执行所有工具
                    if len(actions_to_execute) > 1:
                        logger.info(f"Executing {len(actions_to_execute)} actions in parallel")
                        
                        # 发送并行行动开始事件
                        for action in actions_to_execute:
                            yield AgentEvent(
                                type=AgentEventType.ACTION,
                                data={
                                    "tool": action.get("tool"),
                                    "method": action.get("method", "execute"),
                                    "arguments": action.get("arguments", {}),
                                    "parallel": True
                                },
                                iteration=iteration,
                                tool_name=action.get("tool")
                            )
                        
                        # 并行执行
                        async def execute_action(act):
                            try:
                                # 自动注入上下文参数（如 memory_service 的 session_id）
                                tool_name = act.get("tool")
                                arguments = self._inject_context_params(tool_name, act.get("arguments", {}))
                                
                                return await asyncio.wait_for(
                                    self.skill_executor.execute(
                                        skill_name=tool_name,
                                        method=act.get("method", "execute"),
                                        arguments=arguments
                                    ),
                                    timeout=settings.AGENT_TOOL_TIMEOUT
                                )
                            except asyncio.TimeoutError:
                                return {
                                    "success": False,
                                    "error": f"工具 {act.get('tool')} 执行超时",
                                    "result": None,
                                    "execution_time": settings.AGENT_TOOL_TIMEOUT
                                }
                        
                        execution_results = await asyncio.gather(
                            *[execute_action(act) for act in actions_to_execute],
                            return_exceptions=True
                        )
                        
                        # 发送所有观察事件
                        combined_observations = []
                        for i, (action, result) in enumerate(zip(actions_to_execute, execution_results)):
                            if isinstance(result, Exception):
                                result = {"success": False, "error": str(result), "result": None}
                            
                            yield AgentEvent(
                                type=AgentEventType.OBSERVATION,
                                data=result,
                                iteration=iteration,
                                tool_name=action.get("tool"),
                                execution_time=result.get("execution_time")
                            )
                            
                            combined_observations.append({
                                "tool": action.get("tool"),
                                "action": action,
                                "result": result
                            })
                            
                            if result.get("success"):
                                observations.append({
                                    "tool": action.get("tool"),
                                    "result": result.get("result")
                                })
                        
                        # 更新历史（并行结果合并）
                        history.append({
                            "thought": step_result.get("thought"),
                            "actions": actions_to_execute,
                            "observations": combined_observations
                        })
                    
                    else:
                        # 单个工具执行（原有逻辑）
                        action = actions_to_execute[0]
                        tool_name = action.get("tool")
                        method = action.get("method", "execute")
                        arguments = action.get("arguments", {})
                        
                        # 自动注入上下文参数（如 memory_service 的 session_id）
                        arguments = self._inject_context_params(tool_name, arguments)
                        
                        # 发送行动事件
                        yield AgentEvent(
                            type=AgentEventType.ACTION,
                            data={
                                "tool": tool_name,
                                "method": method,
                                "arguments": arguments
                            },
                            iteration=iteration,
                            tool_name=tool_name
                        )
                        
                        # 执行工具（带超时控制）
                        try:
                            execution_result = await asyncio.wait_for(
                                self.skill_executor.execute(
                                    skill_name=tool_name,
                                    method=method,
                                    arguments=arguments
                                ),
                                timeout=settings.AGENT_TOOL_TIMEOUT
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"Tool {tool_name} timeout after {settings.AGENT_TOOL_TIMEOUT}s")
                            execution_result = {
                                "success": False,
                                "error": f"工具 {tool_name} 执行超时（{settings.AGENT_TOOL_TIMEOUT}秒）",
                                "result": None,
                                "execution_time": settings.AGENT_TOOL_TIMEOUT
                            }
                        
                        # 发送观察事件
                        yield AgentEvent(
                            type=AgentEventType.OBSERVATION,
                            data=execution_result,
                            iteration=iteration,
                            tool_name=tool_name,
                            execution_time=execution_result.get("execution_time")
                        )
                        
                        # 更新历史
                        history.append({
                            "thought": step_result.get("thought"),
                            "action": action,
                            "observation": execution_result
                        })
                        
                        # 记录成功的观察结果
                        if execution_result.get("success"):
                            observations.append({
                                "tool": tool_name,
                                "result": execution_result.get("result")
                            })
                        
                        # 如果工具执行失败，尝试错误恢复
                        if not execution_result.get("success"):
                            recovery_action = await self._handle_error(
                                task, action, execution_result.get("error", "Unknown error")
                            )
                            if recovery_action:
                                history[-1]["recovery"] = recovery_action
                

            except Exception as e:
                logger.error(f"ReAct iteration {iteration} failed: {e}")
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": str(e), "iteration": iteration}
                )
        
        # 达到最大迭代次数，生成总结答案
        logger.warning(f"Reached max iterations ({self.max_iterations})")
        
        final_answer = await self._generate_final_answer(task, observations)
        yield AgentEvent(
            type=AgentEventType.FINAL_ANSWER,
            data=final_answer,
            iteration=self.max_iterations,
            execution_time=time.time() - start_time
        )
        
        yield AgentEvent(
            type=AgentEventType.COMPLETE,
            data={
                "iterations": self.max_iterations,
                "total_time": time.time() - start_time,
                "tools_used": [obs["tool"] for obs in observations],
                "max_iterations_reached": True
            }
        )
    
    def _get_available_tools(
        self,
        enabled_tools: Optional[List[str]],
        disabled_tools: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        all_tools = self.skill_executor.get_available_tools()
        
        if enabled_tools is not None:
            all_tools = [t for t in all_tools if t["name"] in enabled_tools]
        
        if disabled_tools:
            all_tools = [t for t in all_tools if t["name"] not in disabled_tools]
        
        return all_tools
    
    def _build_system_prompt(
        self,
        available_tools: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """构建系统提示词"""
        tools_text = format_tool_list(available_tools)
        context_text = self._format_context(context) if context else "无额外上下文"
        
        return AGENT_SYSTEM_PROMPT.format(
            available_tools=tools_text,
            context=context_text,
            current_date=datetime.now().strftime("%Y-%m-%d")
        )
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """格式化上下文信息"""
        parts = []
        
        # 会话信息
        if "session_id" in context:
            turn_count = context.get('turn_count', 0)
            message_count = context.get('message_count', 0)
            session_info = f"**当前会话**: session_id=`{context['session_id']}`, 已有 {turn_count} 轮对话（共 {message_count} 条消息）"
            if turn_count > 4:
                session_info += "\n> 💡 如需回顾历史对话，请使用 `memory_service.search()` 或 `memory_service.get_recent()`"
            parts.append(session_info)
        
        # 简短对话的最近上下文（自动注入）
        if "recent_context" in context:
            parts.append(f"**最近对话：**\n{context['recent_context']}")
        
        # 图片分析结果
        if "image_analysis" in context:
            parts.append(f"**图片分析：**\n{context['image_analysis']}")
        
        return "\n\n".join(parts) if parts else "新会话，无历史上下文"
    
    async def _think(
        self,
        task: str,
        history: List[Dict[str, Any]],
        system_prompt: str
    ) -> Dict[str, Any]:
        """
        思考阶段：调用 LLM 进行推理
        
        Returns:
            包含 thought 和 action/final_answer 的字典
        """
        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": REACT_STEP_PROMPT.format(
                task=task,
                history=format_history(history)
            )}
        ]
        
        # 调用 LLM（带超时控制）
        try:
            response = await asyncio.wait_for(
                self.llm_service.chat_completion(
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=settings.AGENT_DEFAULT_MAX_TOKENS
                ),
                timeout=settings.AGENT_LLM_CALL_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"LLM call timeout after {settings.AGENT_LLM_CALL_TIMEOUT}s, continuing with timeout notice")
            # 返回一个让Agent意识到超时并继续的响应，而不是抛出异常
            return {
                "thought": f"上一步LLM调用超时（{settings.AGENT_LLM_CALL_TIMEOUT}秒），需要调整策略继续执行任务。",
                "action": None  # 没有action，让下一轮迭代重新思考
            }
        
        content = response.get("content", "")
        
        # 解析 JSON 响应
        return self._parse_llm_response(content)
    
    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """解析 LLM 响应，提取 JSON"""
        # 1. 尝试提取 Markdown 代码块中的 JSON
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 2. 尝试寻找最外层的 {}
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                json_str = content[start:end+1]
            else:
                json_str = content.strip()
        
        try:
            # 尝试修复常见的 JSON 错误 (如 newlines in strings)
            # 简单替换：将非转义的换行符替换为 \n（这很危险，仅作为最后尝试）
            # 这里先尝试标准解析
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError:
            pass

        # 3. 如果 JSON 解析失败，尝试用正则提取关键字段
        # 这种情况通常发生在 LLM 生成了不合法的 JSON (例如字符串里有换行)
        logger.warning(f"JSONDecodeError, attempting regex extraction. Content prefix: {content[:100]}")
        
        fallback_result = {}
        
        # 提取 thought
        thought_match = re.search(r'"thought"\s*:\s*"(.*?)"', json_str, re.DOTALL)
        if thought_match:
            fallback_result["thought"] = thought_match.group(1)
            
        # 提取 final_answer (最重要)
        # 尝试匹配 "final_answer": "..." 
        # 注意：这无法处理嵌套引号，但在 fallback 场景下比直接返回 raw json 好
        final_answer_match = re.search(r'"final_answer"\s*:\s*"(.*)"\s*}?\s*$', json_str, re.DOTALL)
        if final_answer_match:
            fallback_result["final_answer"] = final_answer_match.group(1)
        
        if fallback_result:
            # 如果提取到了任何东西，就返回它
            if "thought" not in fallback_result:
                fallback_result["thought"] = "（解析思考过程时出错）"
            return fallback_result

        # 4. 彻底失败，只能返回原始文本，但做一些清理
        # 如果看起来像 JSON 但失败了，尝试直接把整个 content 当作 final_answer 可能会很丑
        # 我们尝试移除 JSON 的包装
        cleaned_content = content
        if start != -1 and end != -1:
             # 如果是 "{ ... }" 结构但解析失败，可能是 key-value 结构
             pass

        logger.warning(f"Failed to parse LLM response as JSON: {content[:200]}")
        return {
            "thought": "JSON 解析失败，显示原始响应",
            "final_answer": content  # 将原始响应作为最终答案
        }
    
    def _is_duplicate_action(self, action: Dict[str, Any], history: List[Dict[str, Any]]) -> bool:
        """检查 action 是否在历史中重复出现"""
        tool = action.get("tool")
        args = action.get("arguments", {})
        
        # 简单序列化参数进行比较，防止字典顺序问题
        try:
            args_str = json.dumps(args, sort_keys=True)
        except:
            args_str = str(args)

        for step in history:
            prev_actions = []
            if "actions" in step:
                prev_actions.extend(step["actions"])
            elif "action" in step:
                prev_actions.append(step["action"])
            
            for prev_action in prev_actions:
                if prev_action.get("tool") == tool:
                    prev_args = prev_action.get("arguments", {})
                    try:
                        prev_args_str = json.dumps(prev_args, sort_keys=True)
                    except:
                        prev_args_str = str(prev_args)
                        
                    if prev_args_str == args_str:
                        return True
        return False

    async def _handle_error(
        self,
        task: str,
        failed_action: Dict[str, Any],
        error_message: str
    ) -> Optional[Dict[str, Any]]:
        """
        处理错误，尝试恢复
        
        Returns:
            恢复策略或 None
        """
        messages = [
            {"role": "system", "content": "你是一个智能 Agent，需要处理工具调用错误。"},
            {"role": "user", "content": ERROR_RECOVERY_PROMPT.format(
                task=task,
                failed_action=json.dumps(failed_action, ensure_ascii=False),
                error_message=error_message
            )}
        ]
        
        try:
            response = await self.llm_service.chat_completion(
                messages=messages,
                temperature=0.3,  # 低温度以获得更确定的恢复策略
                max_tokens=1024
            )
            
            content = response.get("content", "")
            return self._parse_llm_response(content)
            
        except Exception as e:
            logger.error(f"Error recovery failed: {e}")
            return None
    
    async def _generate_final_answer(
        self,
        task: str,
        observations: List[Dict[str, Any]]
    ) -> str:
        """
        基于收集的信息生成最终答案
        """
        messages = [
            {"role": "system", "content": "你是一个智能助手，需要基于收集的信息生成最终答案。"},
            {"role": "user", "content": FINAL_ANSWER_TEMPLATE.format(
                task=task,
                observations=format_observations(observations)
            )}
        ]
        
        response = await self.llm_service.chat_completion(
            messages=messages,
            temperature=0.5,
            max_tokens=settings.AGENT_DEFAULT_MAX_TOKENS
        )
        
        return response.get("content", "无法生成答案")


# 全局 ReAct 引擎实例
react_engine = ReActEngine()
