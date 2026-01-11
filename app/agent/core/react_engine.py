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
from ..schemas.agent import (
    AgentEvent, 
    AgentEventType, 
    StepResult, 
    ToolAction,
    ExecutionPlan,
    PlanStep,
    PlanStepStatus,
    CompletionResult
)
from .prompt_templates import (
    AGENT_SYSTEM_PROMPT,
    REACT_STEP_PROMPT,
    FINAL_ANSWER_TEMPLATE,
    ERROR_RECOVERY_PROMPT,
    PLAN_GENERATION_PROMPT,
    COMPLETION_CHECK_PROMPT,
    PLAN_GUIDED_REACT_PROMPT,
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
        
        # =====================================================================
        # Phase 1: Plan Generation (Plan-ReAct 混合模型)
        # =====================================================================
        execution_plan: Optional[ExecutionPlan] = None
        
        try:
            execution_plan = await self._generate_plan(task, available_tools)
            
            if execution_plan:
                # 发送计划事件
                yield AgentEvent(
                    type=AgentEventType.PLAN,
                    data={
                        "goal": execution_plan.goal,
                        "approach": execution_plan.approach,
                        "steps": [
                            {
                                "id": step.id,
                                "description": step.description,
                                "tool_hint": step.tool_hint,
                                "status": step.status.value
                            }
                            for step in execution_plan.steps
                        ],
                        "estimated_iterations": execution_plan.estimated_iterations
                    }
                )
                logger.info(f"Plan generated: {len(execution_plan.steps)} steps")
                
                # 如果计划显示不需要工具，直接用 LLM 生成答案
                if not execution_plan.steps:
                    logger.info("No steps in plan, generating direct answer")
                    full_answer = ""
                    async for chunk in self._generate_final_answer(task, []):
                        full_answer += chunk
                        yield AgentEvent(
                            type=AgentEventType.FINAL_ANSWER,
                            data=chunk,
                            iteration=0
                        )
                    
                    yield AgentEvent(
                        type=AgentEventType.COMPLETE,
                        data={
                            "iterations": 0,
                            "total_time": time.time() - start_time,
                            "tools_used": [],
                            "plan_used": False
                        }
                    )
                    return
        except Exception as e:
            logger.warning(f"Plan generation failed, continuing with standard ReAct: {e}")
        
        # =====================================================================
        # Phase 2: ReAct Loop (带计划引导)
        # =====================================================================
        
        success_break = False
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"ReAct iteration {iteration}/{self.max_iterations}")
            
            # 发送迭代开始事件
            yield AgentEvent(
                type=AgentEventType.ITERATION,
                data={"iteration": iteration},
                iteration=iteration
            )
            
            try:
                # 发送早期思考状态事件（让用户立即看到进度）
                yield AgentEvent(
                    type=AgentEventType.THOUGHT,
                    data=f"正在分析问题（第 {iteration} 轮）...",
                    iteration=iteration
                )
                
                # 1. 思考阶段：调用 LLM 进行推理
                step_result = await self._think(
                    task, 
                    history, 
                    system_prompt,
                    execution_plan=execution_plan
                )
                
                # 发送思考结果事件
                yield AgentEvent(
                    type=AgentEventType.THOUGHT,
                    data=step_result.get("thought", ""),
                    iteration=iteration
                )
                
                # 2. 检查是否有最终答案
                # 2. 检查是否有最终答案 (支持旧格式 key 和新格式 Action)
                final_answer_signal = step_result.get("final_answer")
                
                # check for action tool = final_answer
                actions_check = []
                if step_result.get("action"): actions_check = [step_result["action"]]
                elif step_result.get("actions"): actions_check = step_result["actions"]
                
                for act in actions_check:
                    if isinstance(act, dict) and act.get("tool") == "final_answer":
                        final_answer_signal = act.get("thought", "Ready to answer")
                        break

                if final_answer_signal:
                    # =========================================================
                    # 完成度检查 (Completion Check)
                    # =========================================================
                    
                    # 如果是 Action signal (Ready to answer)，说明 Agent 明确表示已完成并准备回答
                    # 此时不需要进行文本完整性检查，直接认为完成
                    if str(final_answer_signal) == "Ready to answer":
                        completion_result = CompletionResult(
                            is_complete=True,
                            confidence=1.0,
                            reasoning="Agent explicit final_answer signal",
                            missing_items=[],
                            suggested_next_steps=[]
                        )
                    else:
                        # 否则对生成的答案文本进行检查
                        completion_result = await self._check_completion(
                            task=task,
                            plan=execution_plan,
                            observations=observations,
                            current_answer=str(final_answer_signal)
                        )
                    
                    # 发送完成度检查事件
                    yield AgentEvent(
                        type=AgentEventType.COMPLETION_CHECK,
                        data={
                            "is_complete": completion_result.is_complete,
                            "confidence": completion_result.confidence,
                            "reasoning": completion_result.reasoning,
                            "missing_items": completion_result.missing_items,
                            "suggested_next_steps": completion_result.suggested_next_steps
                        },
                        iteration=iteration
                    )
                    
                    # 如果未完成且还有迭代次数，继续执行
                    if not completion_result.is_complete and iteration < self.max_iterations:
                        logger.info(f"Completion check: Not complete (confidence: {completion_result.confidence}), continuing...")
                        # 将建议的下一步添加到思考历史，引导 LLM
                        if completion_result.suggested_next_steps:
                            history.append({
                                "thought": f"完成度检查：未完成，缺少 {', '.join(completion_result.missing_items) if completion_result.missing_items else '某些信息'}",
                                "action": None,
                                "observation": {"result": f"建议: {', '.join(completion_result.suggested_next_steps)}"}
                            })
                        continue  # 继续下一轮迭代
                    
                    # 完成或达到上限 -> 退出循环，进入统一的 Final Answer 生成流程
                    success_break = True
                    break
                
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
                
                # CRITICAL Fix: 如果没有动作，必须更新历史，否则 LLM 会陷入死循环
                if not actions_to_execute:
                    logger.warning("No actions generated in this step.")
                    
                    # 检查是否连续多次没有动作 (死循环检测)
                    consecutive_no_action = 0
                    repeated_thought = False
                    
                    # 检查思考是否重复
                    current_thought = step_result.get("thought", "").strip()
                    if history and history[-1].get("thought", "").strip() == current_thought:
                        repeated_thought = True
                        logger.warning(f"Repeated thought detected: {current_thought[:50]}...")
                    
                    for h in reversed(history):
                        if h.get("action") is None and not h.get("actions"):
                            consecutive_no_action += 1
                        else:
                            break
                    
                    # 降低阈值：如果思考重复且无动作，立即干预
                    if consecutive_no_action >= 2 or (repeated_thought and consecutive_no_action >= 1):
                        logger.warning(f"Detected potential infinite loop (no actions for {consecutive_no_action} steps, repeated={repeated_thought}). Forcing final answer prompt.")
                        # 强制注入一个 Observation，引导 LLM 输出最终答案
                        history.append({
                            "thought": step_result.get("thought", "No thought"),
                            "action": None,
                            "observation": {"result": "SYSTEM WARNING: You are in a loop of thinking without acting. Stop thinking and provide the Final Answer immediately using the 'final_answer' JSON format. DO NOT generate more thoughts."}
                        })
                    else:
                        instruction = "No action taken."
                        if repeated_thought:
                            instruction += " You just had this exact same thought. Please change your strategy or provide a Final Answer."
                        else:
                            instruction += " If you have enough information or no tools are needed, you MUST output a JSON with 'final_answer'."
                            
                        history.append({
                            "thought": step_result.get("thought", "No thought"),
                            "action": None,
                            "observation": {"result": instruction}
                        })
                    continue

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
                            duplicate_observations.append({
                                "tool": action.get("tool"),
                                "action": action,
                                "result": dup_obs
                            })
                        else:
                            unique_actions.append(action)
                    
                    # If all actions were duplicates, update history and continue
                    if not unique_actions:
                         history.append({
                            "thought": step_result.get("thought"),
                            "actions": actions_to_execute, 
                            "observations": duplicate_observations
                        })
                         continue
                        
                    actions_to_execute = unique_actions
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
        
        # 循环结束（可能是 break 也可能是达到上限）
        if not success_break:
            logger.warning(f"Reached max iterations ({self.max_iterations})")
        
        # 1. Start streaming final answer
        try:
            full_content = ""
            async for chunk in self._generate_final_answer(task, observations):
                full_content += chunk
                yield AgentEvent(
                    type=AgentEventType.FINAL_ANSWER,
                    data=chunk,  # Yield chunk
                    iteration=self.max_iterations
                )
        except Exception as e:
            logger.error(f"Error generating final answer: {e}")
            yield AgentEvent(
                type=AgentEventType.FINAL_ANSWER,
                data="生成最终答案时出错",
                iteration=self.max_iterations
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
        system_prompt: str,
        execution_plan: Optional[ExecutionPlan] = None
    ) -> Dict[str, Any]:
        """
        思考阶段：调用 LLM 进行推理
        
        Returns:
            包含 thought 和 action/final_answer 的字典
        """
        # 构建消息
        user_prompt = REACT_STEP_PROMPT.format(
            task=task,
            history=format_history(history)
        )
        
        # 如果有计划，使用计划引导的提示词
        if execution_plan:
            current_step = execution_plan.get_current_step()
            step_desc = current_step.description if current_step else "所有步骤已完成"
            plan_summary = self._format_plan_summary(execution_plan)
            
            user_prompt = PLAN_GUIDED_REACT_PROMPT.format(
                task=task,
                plan_summary=plan_summary,
                current_step=step_desc,
                history=format_history(history)
            )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 LLM（带超时控制）
        # 思考阶段使用较少的 max_tokens 加快响应，最终回答阶段再使用完整 tokens
        try:
            response = await asyncio.wait_for(
                self.llm_service.chat_completion(
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=2048  # 思考阶段只需要简短输出，减少等待时间
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
        json_str = ""
        
        # 1. 尝试提取 Markdown 代码块中的 JSON
        # 优化正则：支持 json, jsonc 或无语言标记，支持多行匹配
        json_match = re.search(r"```(?:json|jsonc)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 2. 尝试寻找最外层的 {}
            # 使用栈平衡来找到匹配的括号，或者简单地找第一个 { 和最后一个 }
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                json_str = content[start:end+1]
            else:
                json_str = content.strip()
        
        # 清理常见的 JSON 格式错误
        # 1. 移除行尾逗号 (简单处理)
        # json_str = re.sub(r",\s*}", "}", json_str) # 这太危险
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 3. 如果标准解析失败，尝试用 dirtyjson 或 eval (不安全，跳过) 
        # 尝试修复：有时 LLM 会在 key 中包含换行，或者 value 中包含未转义的引号
        
        logger.warning(f"JSONDecodeError, attempting regex extraction. Content prefix: {content[:100]}")
        
        fallback_result = {}
        
        # 提取 thought
        thought_match = re.search(r'"thought"\s*:\s*"(.*?)"', json_str, re.DOTALL)
        if thought_match:
            fallback_result["thought"] = thought_match.group(1)
            
        # 提取 final_answer (最重要)
        final_answer_match = re.search(r'"final_answer"\s*:\s*"(.*)"\s*}?\s*$', json_str, re.DOTALL)
        if final_answer_match:
            fallback_result["final_answer"] = final_answer_match.group(1)
            
        # 尝试提取 action
        if '"action"' in json_str:
             # 正则提取 action 比较难，这里简单尝试
             pass
        
        if fallback_result:
            if "thought" not in fallback_result:
                fallback_result["thought"] = "（解析思考过程时出错）"
            return fallback_result

        # 4. 彻底失败，只能返回原始文本
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
    ) -> AsyncGenerator[str, None]:
        """
        基于收集的信息生成最终答案（流式）
        
        Yields:
             生成的内容片段
        """
        messages = [
            {"role": "system", "content": "你是一个智能助手，需要基于收集的信息生成最终答案。"},
            {"role": "user", "content": FINAL_ANSWER_TEMPLATE.format(
                task=task,
                observations=format_observations(observations)
            )}
        ]
        
        has_content = False
        async for chunk in self.llm_service.stream_chat_completion(
            messages=messages,
            temperature=0.5,
            max_tokens=settings.AGENT_DEFAULT_MAX_TOKENS
        ):
            content = chunk.get("content", "")
            if content:
                has_content = True
                yield content
        
        if not has_content:
            yield "无法生成答案"
    
    # =========================================================================
    # Plan-ReAct 混合模型方法
    # =========================================================================
    
    async def _generate_plan(
        self,
        task: str,
        available_tools: List[Dict[str, Any]]
    ) -> Optional[ExecutionPlan]:
        """
        生成执行计划
        
        Args:
            task: 用户任务
            available_tools: 可用工具列表
            
        Returns:
            ExecutionPlan 或 None（如果不需要计划）
        """
        tools_text = format_tool_list(available_tools)
        
        messages = [
            {"role": "system", "content": "你是一个智能规划助手，帮助分析任务并生成执行计划。"},
            {"role": "user", "content": PLAN_GENERATION_PROMPT.format(
                task=task,
                tools=tools_text
            )}
        ]
        
        try:
            response = await asyncio.wait_for(
                self.llm_service.chat_completion(
                    messages=messages,
                    temperature=0.3,  # 低温度以获得更确定的计划
                    max_tokens=1024
                ),
                timeout=settings.AGENT_LLM_CALL_TIMEOUT
            )
            
            content = response.get("content", "")
            plan_data = self._parse_llm_response(content)
            
            # 检查是否需要工具
            if not plan_data.get("needs_tools", True) and not plan_data.get("steps"):
                # 简单任务，返回空步骤的计划，以便触发直接回答逻辑
                logger.info("Plan generation: Simple task, returning empty plan for direct answer")
                return ExecutionPlan(
                    goal=plan_data.get("goal", task),
                    approach=plan_data.get("approach", "Direct answer"),
                    steps=[],
                    estimated_iterations=1,
                    is_replanned=False
                )
            
            # 构建 ExecutionPlan
            steps = []
            for step_data in plan_data.get("steps", []):
                steps.append(PlanStep(
                    id=step_data.get("id", f"step_{len(steps)+1}"),
                    description=step_data.get("description", ""),
                    tool_hint=step_data.get("tool_hint"),
                    depends_on=step_data.get("depends_on", []),
                    status=PlanStepStatus.PENDING
                ))
            
            plan = ExecutionPlan(
                goal=plan_data.get("goal", task),
                approach=plan_data.get("approach", ""),
                steps=steps,
                estimated_iterations=plan_data.get("estimated_iterations", 3)
            )
            
            logger.info(f"Generated plan with {len(steps)} steps: {plan.goal}")
            return plan
            
        except asyncio.TimeoutError:
            logger.warning("Plan generation timeout, proceeding without plan")
            return None
        except Exception as e:
            logger.error(f"Plan generation failed: {e}")
            return None
    
    async def _check_completion(
        self,
        task: str,
        plan: Optional[ExecutionPlan],
        observations: List[Dict[str, Any]],
        current_answer: str
    ) -> CompletionResult:
        """
        检查任务是否完成
        
        Args:
            task: 原始任务
            plan: 执行计划（可能为 None）
            observations: 收集的观察结果
            current_answer: 当前生成的回答
            
        Returns:
            CompletionResult
        """
        # 格式化计划摘要
        plan_summary = self._format_plan_summary(plan) if plan else "无预设计划"
        
        # 格式化观察摘要
        obs_summary = format_observations(observations) if observations else "无收集信息"
        
        messages = [
            {"role": "system", "content": "你是一个任务完成度评估助手。"},
            {"role": "user", "content": COMPLETION_CHECK_PROMPT.format(
                task=task,
                plan=plan_summary,
                observations_summary=obs_summary,
                current_answer=current_answer[:2000]  # 限制长度
            )}
        ]
        
        try:
            response = await asyncio.wait_for(
                self.llm_service.chat_completion(
                    messages=messages,
                    temperature=0.2,  # 极低温度以获得确定的判断
                    max_tokens=512
                ),
                timeout=30  # 完成度检查应该快速
            )
            
            content = response.get("content", "")
            result_data = self._parse_llm_response(content)
            
            return CompletionResult(
                is_complete=result_data.get("is_complete", True),
                confidence=result_data.get("confidence", 0.5),
                reasoning=result_data.get("reasoning", ""),
                missing_items=result_data.get("missing_items", []),
                suggested_next_steps=result_data.get("suggested_next_steps", [])
            )
            
        except Exception as e:
            logger.error(f"Completion check failed: {e}")
            # 默认认为完成
            return CompletionResult(
                is_complete=True,
                confidence=0.3,
                reasoning=f"完成度检查失败: {str(e)}"
            )
    
    def _format_plan_summary(self, plan: ExecutionPlan) -> str:
        """格式化计划摘要用于提示词"""
        lines = [
            f"**目标：** {plan.goal}",
            f"**思路：** {plan.approach}",
            "**步骤：**"
        ]
        
        for i, step in enumerate(plan.steps, 1):
            status_icon = {
                PlanStepStatus.PENDING: "⏳",
                PlanStepStatus.IN_PROGRESS: "🔄",
                PlanStepStatus.DONE: "✅",
                PlanStepStatus.FAILED: "❌",
                PlanStepStatus.SKIPPED: "⏭️"
            }.get(step.status, "⏳")
            
            tool_info = f" (使用 {step.tool_hint})" if step.tool_hint else ""
            lines.append(f"{i}. {status_icon} {step.description}{tool_info}")
            
            if step.result_summary:
                lines.append(f"   → {step.result_summary}")
        
        return "\n".join(lines)


# 全局 ReAct 引擎实例
react_engine = ReActEngine()
