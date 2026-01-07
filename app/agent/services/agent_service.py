"""
Agent Service - Business Logic Layer
Orchestrates ReAct engine, memory systems, and tool execution
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from ..config import settings
from ..schemas.agent import (
    AgentEvent,
    AgentEventType,
    AgentRequest,
    AgentResponse
)
from ..core.react_engine import react_engine
from ..core.skill_executor import skill_executor
from ..memory.session_memory import SessionMemory

logger = logging.getLogger(__name__)


def _get_db_session():
    """获取数据库会话"""
    from storage.pgsql.database import get_session
    return get_session()


class AgentService:
    """
    Agent 服务主类
    
    职责：
    1. 协调 ReAct 引擎执行
    2. 管理会话记忆
    3. 生成流式/非流式响应
    """
    
    def __init__(self):
        self.react_engine = react_engine
        self.skill_executor = skill_executor
        
        # 会话缓存（session_id -> (SessionMemory, db_session)）
        self._session_cache: Dict[str, tuple] = {}
        
        # 并发控制 - 限制同时运行的 Agent 请求数量
        self._request_semaphore = asyncio.Semaphore(settings.AGENT_MAX_CONCURRENT_REQUESTS)
        logger.info(f"Agent Service initialized with max concurrent requests: {settings.AGENT_MAX_CONCURRENT_REQUESTS}")
    
    def _get_session(
        self, 
        session_id: Optional[str], 
        user_id: str = "anonymous"
    ) -> SessionMemory:
        """获取或创建会话"""
        if session_id and session_id in self._session_cache:
            return self._session_cache[session_id][0]
        
        db = _get_db_session()
        session = SessionMemory(
            db_session=db,
            session_id=session_id,
            user_id=user_id
        )
        self._session_cache[session.session_id] = (session, db)
        return session
    
    def _commit_session(self, session_id: str) -> None:
        """提交会话更改"""
        if session_id in self._session_cache:
            _, db = self._session_cache[session_id]
            try:
                db.commit()
            except Exception as e:
                logger.error(f"Failed to commit session {session_id}: {e}")
                db.rollback()
    
    def _close_session(self, session_id: str) -> None:
        """关闭会话"""
        if session_id in self._session_cache:
            _, db = self._session_cache[session_id]
            try:
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
            del self._session_cache[session_id]
    
    async def run_agent(
        self,
        request: AgentRequest
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        执行 Agent（包含超时处理和错误捕获）
        
        Args:
            request: Agent 请求
        """
        
        # 获取并发锁
        await self._request_semaphore.acquire()
        
        has_finished = False
        # 确保我们有 session_id，即便是新会话
        # 注意：这里获取 session 会初始化它（如果是新的），_run_agent_internal 也会用到
        session = self._get_session(request.session_id, request.user_id or "anonymous")
        current_session_id = session.session_id
        # 更新 request 中的 session_id，确保内部逻辑使用同一个 ID
        request.session_id = current_session_id
        
        try:
            # 使用超时控制整个请求
            async with asyncio.timeout(settings.AGENT_REQUEST_TIMEOUT):
                async for event in self._run_agent_internal(request):
                    if event.type in [AgentEventType.FINAL_ANSWER, AgentEventType.ERROR]:
                        has_finished = True
                    yield event
                        
        except asyncio.TimeoutError:
            has_finished = True # Error handled below
            error_msg = f"请求超时（{settings.AGENT_REQUEST_TIMEOUT}秒）"
            logger.error(f"Agent request timeout after {settings.AGENT_REQUEST_TIMEOUT}s")
            
            # 记录超时错误到数据库
            if request.session_id:
                try:
                    session = self._get_session(request.session_id, request.user_id or "anonymous")
                    session.add_message("assistant", f"**系统提示**: {error_msg}")
                    self._commit_session(request.session_id)
                except Exception as db_err:
                    logger.error(f"Failed to save timeout error: {db_err}")

            yield AgentEvent(
                type=AgentEventType.ERROR,
                data={
                    "error": error_msg,
                    "timeout": True
                }
            )
        except GeneratorExit:
            logger.warning("Agent request interrupted by client")
            # GeneratorExit needs to be propagated, but we handle the DB save in finally
            raise
        except Exception as e:
            has_finished = True # Error handled below
            logger.error(f"Agent request failed: {e}", exc_info=True)
            
            # 记录异常错误到数据库
            if request.session_id:
                try:
                    session = self._get_session(request.session_id, request.user_id or "anonymous")
                    session.add_message("assistant", f"**系统错误**: {str(e)}")
                    self._commit_session(request.session_id)
                except Exception as db_err:
                    logger.error(f"Failed to save exception error: {db_err}")

            yield AgentEvent(
                type=AgentEventType.ERROR,
                data={
                    "error": str(e),
                    "type": type(e).__name__
                }
            )
        finally:
            # Check if interrupted without final answer or error
            if not has_finished and request.session_id:
                try:
                    logger.info(f"Session {request.session_id} interrupted without final answer, saving placeholder.")
                    session = self._get_session(request.session_id, request.user_id or "anonymous")
                    session.add_assistant_message("(No response generated)")
                    self._commit_session(request.session_id)
                except Exception as e:
                    logger.error(f"Failed to save interruption state: {e}")

            self._request_semaphore.release()
            logger.info(f"Agent request completed (concurrent: {settings.AGENT_MAX_CONCURRENT_REQUESTS - self._request_semaphore._value}/{settings.AGENT_MAX_CONCURRENT_REQUESTS})")
    
    async def _run_agent_internal(
        self,
        request: AgentRequest
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        内部执行逻辑（被 run_agent 包装）
        """
        start_time = time.time()
        user_id = request.user_id or "anonymous"
        session = self._get_session(request.session_id, user_id)
        
        # 添加用户消息到会话
        session.add_user_message(request.message)
        self._commit_session(session.session_id)
        
        # 构建上下文
        context = await self._build_context(
            session=session,
            extra_context=request.context
        )
        
        # 如果有图片，使用 OCR + LLM 分析并提取信息
        if request.images:
            image_analysis = await self._analyze_images(
                images=request.images,
                user_message=request.message
            )
            if image_analysis:
                context["image_analysis"] = image_analysis
                
                # 发送图片分析事件
                yield AgentEvent(
                    type=AgentEventType.OBSERVATION,
                    data={
                        "source": "image_analysis",
                        "success": True,
                        "result": image_analysis
                    }
                )
        
        # 发送意图识别事件
        intent_event = await self._recognize_intent(request.message)
        # Inject session_id into intent data
        if isinstance(intent_event.data, dict):
            intent_event.data["session_id"] = session.session_id
        yield intent_event
        
        # 收集事件用于后处理
        all_events: List[AgentEvent] = [intent_event]
        final_answer = None
        tools_used = []
        
        # 运行 ReAct 引擎
        async for event in self.react_engine.run(
            task=request.message,
            context=context,
            enabled_tools=request.enabled_tools,
            disabled_tools=request.disabled_tools
        ):
            yield event
            all_events.append(event)
            
            # 保存思考过程到会话
            if event.type == AgentEventType.THOUGHT:
                session.add_message(
                    role="assistant",
                    content=f"[思考] {event.data}" if event.data else "[思考中...]"
                )
                self._commit_session(session.session_id)
            
            # 保存工具调用
            if event.type == AgentEventType.ACTION and event.tool_name:
                tools_used.append(event.tool_name)
                action_data = event.data if isinstance(event.data, dict) else {}
                session.add_message(
                    role="tool",
                    content=f"[调用工具: {event.tool_name}]",
                    tool_name=event.tool_name,
                    tool_result={"action": action_data}
                )
                self._commit_session(session.session_id)
            
            # 保存工具执行结果
            if event.type == AgentEventType.OBSERVATION:
                obs_data = event.data if isinstance(event.data, dict) else {"result": str(event.data)}
                tool_name = event.tool_name or "unknown"
                success = obs_data.get("success", True) if isinstance(obs_data, dict) else True
                session.add_message(
                    role="tool",
                    content=f"[工具结果: {tool_name}] {'成功' if success else '失败'}",
                    tool_name=tool_name,
                    tool_result=obs_data
                )
                self._commit_session(session.session_id)
            
            # 收集最终答案
            if event.type == AgentEventType.FINAL_ANSWER:
                final_answer = event.data
        
        # 添加最终答案到会话
        if final_answer:
            session.add_assistant_message(str(final_answer))
            self._commit_session(session.session_id)
            
            # 异步生成会话标题（后台执行，不阻塞响应）
            asyncio.create_task(self.generate_session_title(session.session_id, user_id))
    
    async def run_agent_sync(
        self,
        request: AgentRequest
    ) -> AgentResponse:
        """
        同步执行 Agent 任务
        
        Args:
            request: Agent 请求
            
        Returns:
            AgentResponse 响应
        """
        start_time = time.time()
        events: List[AgentEvent] = []
        
        async for event in self.run_agent(request):
            events.append(event)
        
        # 提取结果
        final_answer = ""
        iterations = 0
        tools_used = []
        
        for event in events:
            if event.type == AgentEventType.FINAL_ANSWER:
                final_answer = str(event.data)
            if event.type == AgentEventType.COMPLETE:
                if isinstance(event.data, dict):
                    iterations = event.data.get("iterations", 0)
                    tools_used = event.data.get("tools_used", [])
            if event.type == AgentEventType.ACTION and event.tool_name:
                if event.tool_name not in tools_used:
                    tools_used.append(event.tool_name)
        
        session = self._get_session(request.session_id, request.user_id or "anonymous")
        
        return AgentResponse(
            session_id=session.session_id,
            message_id=str(uuid4())[:8],
            answer=final_answer or "无法生成回答",
            iterations=iterations,
            tools_used=tools_used,
            started_at=datetime.utcfromtimestamp(start_time),
            completed_at=datetime.utcnow(),
            total_time=time.time() - start_time
        )
    
    async def _build_context(
        self,
        session: SessionMemory,
        extra_context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """构建执行上下文"""
        context = {}
        
        # 会话历史摘要
        if session.session.message_count and session.session.message_count > 0:
            context["session_history"] = session.get_summary()
        
        # 额外上下文
        if extra_context:
            context.update(extra_context)
        
        return context
    
    async def _recognize_intent(self, message: str) -> AgentEvent:
        """识别用户意图"""
        # 使用 Skill 匹配来推断意图
        matched_tools = self.skill_executor.match_tools(message, top_n=3)
        
        intent = {
            "message": message[:100],
            "suggested_tools": matched_tools,
            "complexity": "moderate" if len(matched_tools) > 1 else "simple"
        }
        
        return AgentEvent(
            type=AgentEventType.INTENT,
            data=intent
        )
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取所有可用工具"""
        return self.skill_executor.get_available_tools()
    
    def get_session_history(
        self, 
        session_id: str,
        user_id: str = "anonymous",
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        获取会话历史
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            limit: 限制消息数量
        """
        session = self._get_session(session_id, user_id)
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "messages": session.get_messages(limit=limit),
            "message_count": session.session.message_count,
            "total_tokens": session.session.total_tokens,
            "created_at": session.session.created_at.isoformat() if session.session.created_at else None,
            "updated_at": session.session.updated_at.isoformat() if session.session.updated_at else None,
        }
    
    def list_user_sessions(
        self, 
        user_id: str, 
        limit: int = 20,
        include_archived: bool = False
    ) -> List[Dict[str, Any]]:
        """
        列出用户的所有会话
        
        Args:
            user_id: 用户ID
            limit: 最大返回数量
            include_archived: 是否包含已归档会话
        """
        from storage.pgsql.models import AgentSession
        db = _get_db_session()
        
        try:
            query = db.query(AgentSession).filter(
                AgentSession.user_id == user_id
            )
            
            if not include_archived:
                query = query.filter(AgentSession.is_archived == False)
            
            sessions = query.order_by(AgentSession.updated_at.desc()).limit(limit).all()
            
            return [s.to_dict() for s in sessions]
        finally:
            db.close()
    
    def clear_session(self, session_id: str) -> bool:
        """清除会话"""
        if session_id in self._session_cache:
            session, _ = self._session_cache[session_id]
            session.clear()
            self._commit_session(session_id)
            return True
        return False
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        from storage.pgsql.models import AgentSession, AgentMessage
        
        self._close_session(session_id)
        
        db = _get_db_session()
        try:
            # 删除相关的 agent messages
            db.query(AgentMessage).filter(AgentMessage.session_id == session_id).delete()
            # 删除 session
            result = db.query(AgentSession).filter(AgentSession.id == session_id).delete()
            db.commit()
            return result > 0
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete session: {e}")
            return False
        finally:
            db.close()
            
    def delete_message(self, session_id: str, message_id: str, include_following: bool = False) -> bool:
        """
        删除消息
        
        Args:
            session_id: 会话ID
            message_id: 消息ID
            include_following: 是否同时删除之后的所有消息
        """
        session = self._get_session(session_id)
        try:
            if include_following:
                count = session.delete_messages_after(message_id, include_target=True)
                success = count > 0
            else:
                success = session.delete_message(message_id)
            
            self._commit_session(session_id)
            return success
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
            return False
    
    async def _analyze_images(
        self,
        images: List[str],
        user_message: str
    ) -> Optional[Dict[str, Any]]:
        """
        使用 OCR + LLM 分析图片内容
        
        Args:
            images: 图片列表（URL 或路径）
            user_message: 用户消息/需求
            
        Returns:
            分析结果或 None
        """
        try:
            from .vlm_service import vlm_service
            
            # 使用 OCR + LLM 提取信息
            result = await vlm_service.extract_information(
                images=images,
                user_context=user_message,
                extraction_focus=["文字内容", "关键数据", "可视化信息"]
            )
            
            if result.get("success"):
                extracted = result.get("extracted") or result.get("raw_response")
                return {
                    "images_count": len(images),
                    "extracted_info": extracted,
                    "model": result.get("model")
                }
            else:
                logger.warning(f"Image analysis failed: {result.get('error')}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to analyze images: {e}")
            return None
    
    async def analyze_images_standalone(
        self,
        images: List[str],
        user_message: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        独立的图片分析接口（不运行完整 Agent 流程）
        
        Args:
            images: 图片列表
            user_message: 用户消息
            user_id: 用户ID（可选）
            
        Returns:
            分析结果
        """
        try:
            from .vlm_service import vlm_service
            
            result = await vlm_service.analyze_image(
                images=images,
                user_message=user_message
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Standalone image analysis failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def generate_session_title(self, session_id: str, user_id: str = "anonymous"):
        """
        使用 LLM 为 Agent 会话生成标题（异步）
        """
        from storage.pgsql.models import AgentSession
        
        db = _get_db_session()
        try:
            # 获取会话
            session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
            if not session:
                logger.warning(f"Agent session {session_id} not found for title generation")
                return
            
            # 如果已有标题且不是默认值，跳过
            default_titles = ["New Chat", "新对话", None, ""]
            if session.title and session.title not in default_titles:
                logger.debug(f"Session {session_id} already has custom title: {session.title}")
                return
            
            # 获取会话内存以读取消息
            session_memory = self._get_session(session_id, user_id)
            messages = session_memory.get_messages(limit=3)
            
            if not messages:
                logger.warning(f"No messages found for session {session_id}")
                return
            
            # 只取第一条用户消息来生成标题
            user_message = None
            for msg in messages:
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break
            
            if not user_message:
                logger.info(f"No user message found in session {session_id}")
                return
            
            # 使用 LLM 生成标题
            from services.llm_service.client import LLMServiceClient
            llm = LLMServiceClient()
            
            prompt = [
                {"role": "system", "content": "Generate a concise (max 20 chars) title for this conversation. Return ONLY the title text, no quotes or prefixes. Language should match the user's message."},
                {"role": "user", "content": user_message},
                {"role": "user", "content": "Generate a title."}
            ]
            
            response = await llm.async_chat_completion(
                messages=prompt,
                max_tokens=30,
                temperature=0.5
            )
            
            title = response.get("content", "").strip().strip('"').strip("'")[:50]
            
            if title:
                session.title = title
                db.commit()
                logger.info(f"Generated title for agent session {session_id}: {title}")
            
        except Exception as e:
            logger.error(f"Error generating agent session title: {e}")
        finally:
            db.close()


# 全局 Agent 服务实例
agent_service = AgentService()
