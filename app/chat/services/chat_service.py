"""
Chat Service - Business Logic Layer
Handles chat sessions, messages, and context management
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime
from uuid import UUID
import time
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc

from ..config import settings
from ..database import Session, Message, get_session # 使用统一的模型别名
from ..schemas.chat import (
    SessionCreate,
    SessionUpdate,
    ChatRequest,
    ChatMessage,
    MessageRole
)
from .llm_service import LLMService, llm_service

# OCR 客户端
try:
    from services.ocr_service.client import OCRServiceClient
    OCR_AVAILABLE = True
except ImportError:
    import sys
    sys.path.insert(0, '/app')
    try:
        from services.ocr_service.client import OCRServiceClient
        OCR_AVAILABLE = True
    except ImportError:
        OCR_AVAILABLE = False
        OCRServiceClient = None

logger = logging.getLogger(__name__)


class ChatService:
    """
    聊天服务类
    处理会话管理、消息存储和上下文管理
    """
    
    def __init__(self, llm: Optional[LLMService] = None):
        """
        初始化聊天服务
        
        Args:
            llm: LLM服务实例，默认使用全局实例
        """
        self.llm = llm or llm_service
        
        # OCR 客户端
        self.ocr_client = None
        self.ocr_executor = None
        if OCR_AVAILABLE:
            import os
            ocr_host = os.getenv("OCR_HOST", "ocr_service")
            ocr_port = os.getenv("OCR_PORT", "8001")
            self.ocr_client = OCRServiceClient(base_url=f"http://{ocr_host}:{ocr_port}")
            self.ocr_executor = ThreadPoolExecutor(max_workers=3)
    
    
    async def generate_session_title(self, session_id: str):
        """
        使用LLM为会话生成标题（异步）
        """
        db = get_session()
        try:
            session = self.get_session(db, session_id)
            if not session:
                logger.warning(f"Session {session_id} not found in background task")
                return
            
            logger.info(f"Checking title for session {session_id}: current title='{session.title}'")
            
            # 如果已有标题且不是默认值，跳过
            default_titles = ["New Chat", "新对话"]
            if session.title and session.title not in default_titles:
                logger.debug("Session already has custom title, skipping")
                return
            
            # 获取前5条消息作为上下文
            messages = self.get_session_messages(db, session_id, limit=5)
            if not messages:
                logger.warning("No messages found for session")
                return
            
            # 只有当包含用户消息时才生成
            if not any(m.role == "user" for m in messages):
                logger.info("No user messages yet")
                return

            logger.info("Generating title from messages...")

            prompt = [
                {"role": "system", "content": "You are a helpful assistant. Generate a concise (max 30 chars) title for this conversation. Return ONLY the title text, no quotes or prefixes. Language should match the conversation content."},
            ]
            
            for msg in messages:
                prompt.append({"role": "user" if msg.role == "user" else "assistant", "content": msg.content})
                
            prompt.append({"role": "user", "content": "Generate a title."})

            # 调用LLM
            response = await self.llm.async_chat_completion(
                messages=prompt,
                max_tokens=20,
                temperature=0.5
            )
            
            title = response["content"].strip().strip('"').strip('\'')[:50]
            
            if title:
                session.title = title
                db.commit()
                logger.info(f"Generated title for session {session_id}: {title}")
                
        except Exception as e:
            logger.error(f"Error generating session title: {e}")
        finally:
            db.close()

    # ==================== Image OCR Processing ====================
    
    async def _ocr_images(self, images: List[str]) -> str:
        """
        异步处理图片列表，使用 OCR 提取文本
        
        Args:
            images: base64 编码的图片列表
            
        Returns:
            合并的 OCR 文本结果
        """
        if not self.ocr_client or not images:
            return ""
        
        all_texts = []
        
        for i, img_data in enumerate(images, 1):
            try:
                # 处理 data URL 格式
                if "," in img_data:
                    # data:image/png;base64,xxxxx 格式
                    image_base64 = img_data.split(",", 1)[1]
                else:
                    image_base64 = img_data
                
                # 使用线程池异步调用同步 OCR
                loop = asyncio.get_event_loop()
                ocr_result = await loop.run_in_executor(
                    self.ocr_executor,
                    self.ocr_client.ocr,
                    image_base64
                )
                
                # 解析 OCR 结果
                text = self._parse_ocr_result(ocr_result)
                if text:
                    all_texts.append(f"【图片 {i} 识别内容】\n{text}")
                    
            except Exception as e:
                logger.warning(f"OCR failed for image {i}: {e}")
                all_texts.append(f"【图片 {i}】（识别失败）")
        
        return "\n\n".join(all_texts) if all_texts else ""
    
    def _parse_ocr_result(self, ocr_result: Any) -> str:
        """解析 OCR 返回结果"""
        if isinstance(ocr_result, list):
            texts = []
            for item in ocr_result:
                if isinstance(item, dict) and 'text' in item:
                    texts.append(item['text'])
                elif isinstance(item, list) and len(item) > 1:
                    # 格式: [[box, (text, confidence)], ...]
                    if isinstance(item[1], tuple):
                        texts.append(item[1][0])
                elif isinstance(item, str):
                    texts.append(item)
            return "\n".join(texts)
        elif isinstance(ocr_result, dict):
            return ocr_result.get('text', str(ocr_result))
        else:
            return str(ocr_result)

    # ==================== Session Management ====================

    
    def create_session(
        self,
        db: DBSession,
        data: SessionCreate
    ) -> Session:
        """
        创建新会话
        
        Args:
            db: 数据库会话
            data: 会话创建数据
            
        Returns:
            创建的会话
        """
        session = Session(
            title=data.title or "新对话",
            model=data.model or settings.CHAT_LLM_MODEL_NAME,
            system_prompt=data.system_prompt,
            temperature=str(data.temperature) if data.temperature else "0.7",
            max_tokens=data.max_tokens or settings.DEFAULT_MAX_TOKENS,
            top_p=str(data.top_p) if data.top_p else "0.9",
            user_id=data.user_id,
            extra_data=data.extra_data
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        
        logger.info(f"Created new session: {session.id}")
        return session
    
    def get_session(
        self,
        db: DBSession,
        session_id: str
    ) -> Optional[Session]:
        """
        获取会话
        
        Args:
            db: 数据库会话
            session_id: 会话ID
            
        Returns:
            会话对象或None
        """
        try:
            uuid_id = UUID(session_id)
            return db.query(Session).filter(Session.id == uuid_id).first()
        except ValueError:
            logger.error(f"Invalid session ID format: {session_id}")
            return None
    
    def update_session(
        self,
        db: DBSession,
        session_id: str,
        data: SessionUpdate
    ) -> Optional[Session]:
        """
        更新会话
        
        Args:
            db: 数据库会话
            session_id: 会话ID
            data: 更新数据
            
        Returns:
            更新后的会话或None
        """
        session = self.get_session(db, session_id)
        if not session:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        
        for key, value in update_data.items():
            if key in ['temperature', 'top_p'] and value is not None:
                value = str(value)
            setattr(session, key, value)
        
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(session)
        
        logger.info(f"Updated session: {session_id}")
        return session
    
    def delete_session(
        self,
        db: DBSession,
        session_id: str
    ) -> bool:
        """
        删除会话（及其所有消息）
        
        Args:
            db: 数据库会话
            session_id: 会话ID
            
        Returns:
            是否删除成功
        """
        session = self.get_session(db, session_id)
        if not session:
            return False
        
        db.delete(session)
        db.commit()
        
        logger.info(f"Deleted session: {session_id}")
        return True
    
    def list_sessions(
        self,
        db: DBSession,
        user_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False
    ) -> tuple[List[Session], int]:
        """
        列出会话
        
        Args:
            db: 数据库会话
            user_id: 用户ID过滤
            page: 页码
            page_size: 每页数量
            include_archived: 是否包含已归档会话
            
        Returns:
            (会话列表, 总数)
        """
        query = db.query(Session)
        
        if user_id:
            query = query.filter(Session.user_id == user_id)
        
        if not include_archived:
            query = query.filter(Session.is_archived == False)
        
        total = query.count()
        
        sessions = (
            query
            .order_by(desc(Session.updated_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        
        return sessions, total
    
    # ==================== Message Management ====================
    
    def add_message(
        self,
        db: DBSession,
        session_id: str,
        role: str,
        content: str,
        model: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        finish_reason: Optional[str] = None,
        extra_data: Optional[Dict] = None
    ) -> Message:
        """
        添加消息到会话
        
        Args:
            db: 数据库会话
            session_id: 会话ID
            role: 消息角色
            content: 消息内容
            model: 使用的模型
            prompt_tokens: 输入tokens
            completion_tokens: 输出tokens
            total_tokens: 总tokens
            finish_reason: 完成原因
            extra_data: 额外元数据
            
        Returns:
            创建的消息
        """
        message = Message(
            session_id=UUID(session_id),
            role=role,
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            finish_reason=finish_reason,
            extra_data=extra_data
        )
        
        db.add(message)
        
        # 更新会话时间
        session = self.get_session(db, session_id)
        if session:
            session.updated_at = datetime.utcnow()
            # Legacy title generation removed
        
        db.commit()
        db.refresh(message)
        
        return message
    
    def get_session_messages(
        self,
        db: DBSession,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Message]:
        """
        获取会话的所有消息
        
        Args:
            db: 数据库会话
            session_id: 会话ID
            limit: 最大消息数量
            
        Returns:
            消息列表（按时间升序）
        """
        try:
            uuid_id = UUID(session_id)
            
            if limit:
                # 获取最近的N条消息（先按时间降序取limit条，再反转恢复升序）
                subquery = (
                    db.query(Message)
                    .filter(Message.session_id == uuid_id)
                    .order_by(desc(Message.created_at))
                    .limit(limit)
                    .subquery()
                )
                # 使用子查询并按升序排序
                messages = (
                    db.query(Message)
                    .filter(Message.id.in_(db.query(subquery.c.id)))
                    .order_by(Message.created_at)
                    .all()
                )
                return messages
            
            # 没有limit时，直接按时间升序获取所有消息
            return (
                db.query(Message)
                .filter(Message.session_id == uuid_id)
                .order_by(Message.created_at)
                .all()
            )
            
        except ValueError:
            logger.error(f"Invalid session ID format: {session_id}")
            return []
    
    def build_context_messages(
        self,
        db: DBSession,
        session: Session,
        max_messages: Optional[int] = None,
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        构建上下文消息列表（用于发送给LLM）
        
        Args:
            db: 数据库会话
            session: 会话对象
            max_messages: 最大消息数量
            max_tokens: 最大token数量
            
        Returns:
            OpenAI格式的消息列表
        """
        max_messages = max_messages or settings.MAX_CONTEXT_MESSAGES
        max_tokens = max_tokens or settings.MAX_CONTEXT_TOKENS
        
        messages = []
        
        # 添加系统提示词
        if session.system_prompt:
            messages.append({
                "role": "system",
                "content": session.system_prompt
            })
        
        # 获取历史消息
        history = self.get_session_messages(db, str(session.id), limit=max_messages)
        
        # 计算token并截断
        total_tokens = self.llm.estimate_tokens(session.system_prompt or "")
        
        for msg in history:
            msg_tokens = self.llm.estimate_tokens(msg.content)
            if total_tokens + msg_tokens > max_tokens:
                break
            
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
            total_tokens += msg_tokens
        
        return messages
    
    # ==================== Chat Completion ====================
    
    def chat(
        self,
        db: DBSession,
        request: ChatRequest
    ) -> Dict[str, Any]:
        """
        同步聊天完成
        
        Args:
            db: 数据库会话
            request: 聊天请求
            
        Returns:
            聊天响应
        """
        # 获取或创建会话
        session = None
        if request.session_id:
            session = self.get_session(db, request.session_id)
        
        if not session:
            # 创建新会话
            session = self.create_session(db, SessionCreate(
                model=request.model,
                user_id=request.user_id
            ))
        
        # 构建消息
        if request.message:
            # 简化形式：只有一条用户消息
            user_content = request.message
        elif request.messages:
            # 获取最后一条用户消息
            user_messages = [m for m in request.messages if m.role == MessageRole.USER]
            if user_messages:
                user_content = user_messages[-1].content
            else:
                raise ValueError("No user message provided")
        else:
            raise ValueError("Either 'message' or 'messages' must be provided")
        
        # 保存用户消息
        self.add_message(db, str(session.id), "user", user_content)
        
        # 构建上下文
        context_messages = self.build_context_messages(db, session)
        
        # 调用LLM
        temperature = request.temperature or float(session.temperature)
        max_tokens = request.max_tokens or session.max_tokens
        top_p = request.top_p or float(session.top_p)
        model = request.model or session.model
        
        response = self.llm.chat_completion(
            messages=context_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )
        
        # 保存助手消息
        self.add_message(
            db,
            str(session.id),
            "assistant",
            response["content"],
            model=response["model"],
            prompt_tokens=response["usage"]["prompt_tokens"],
            completion_tokens=response["usage"]["completion_tokens"],
            total_tokens=response["usage"]["total_tokens"],
            finish_reason=response["finish_reason"]
        )
        
        # 构建响应
        return {
            "id": response["id"],
            "object": "chat.completion",
            "created": response["created"],
            "model": response["model"],
            "session_id": str(session.id),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response["content"]
                },
                "finish_reason": response["finish_reason"]
            }],
            "usage": response["usage"]
        }
    
    async def async_chat(
        self,
        db: DBSession,
        request: ChatRequest
    ) -> Dict[str, Any]:
        """
        异步聊天完成
        
        Args:
            db: 数据库会话
            request: 聊天请求
            
        Returns:
            聊天响应
        """
        # 获取或创建会话
        session = None
        if request.session_id:
            session = self.get_session(db, request.session_id)
        
        if not session:
            session = self.create_session(db, SessionCreate(
                model=request.model,
                user_id=request.user_id
            ))
        
        # 构建消息
        if request.message:
            user_content = request.message
        elif request.messages:
            user_messages = [m for m in request.messages if m.role == MessageRole.USER]
            if user_messages:
                user_content = user_messages[-1].content
            else:
                raise ValueError("No user message provided")
        else:
            raise ValueError("Either 'message' or 'messages' must be provided")
        
        # 处理图片 OCR（如果有）
        ocr_context = ""
        if request.images:
            logger.info(f"Processing {len(request.images)} images with OCR...")
            ocr_context = await self._ocr_images(request.images)
            if ocr_context:
                logger.info(f"OCR extracted {len(ocr_context)} characters from images")
        
        # 如果有 OCR 结果，追加到用户消息中
        message_to_save = user_content
        if ocr_context:
            user_content = f"{user_content}\n\n{ocr_context}"
        
        # 保存用户消息
        self.add_message(db, str(session.id), "user", message_to_save)
        
        # 构建上下文
        context_messages = self.build_context_messages(db, session)
        
        # 如果有 OCR 结果，替换最后一条用户消息的内容（加入 OCR）
        if ocr_context and context_messages:
            for i in range(len(context_messages) - 1, -1, -1):
                if context_messages[i].get("role") == "user":
                    context_messages[i]["content"] = user_content
                    break
        
        # 调用LLM
        temperature = request.temperature or float(session.temperature)
        max_tokens = request.max_tokens or session.max_tokens
        top_p = request.top_p or float(session.top_p)
        model = request.model or session.model
        
        response = await self.llm.async_chat_completion(
            messages=context_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )
        
        # 保存助手消息
        self.add_message(
            db,
            str(session.id),
            "assistant",
            response["content"],
            model=response["model"],
            prompt_tokens=response["usage"]["prompt_tokens"],
            completion_tokens=response["usage"]["completion_tokens"],
            total_tokens=response["usage"]["total_tokens"],
            finish_reason=response["finish_reason"]
        )
        
        return {
            "id": response["id"],
            "object": "chat.completion",
            "created": response["created"],
            "model": response["model"],
            "session_id": str(session.id),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response["content"]
                },
                "finish_reason": response["finish_reason"]
            }],
            "usage": response["usage"]
        }
    
    async def async_stream_chat(
        self,
        db: DBSession,
        request: ChatRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        异步流式聊天完成
        
        Args:
            db: 数据库会话
            request: 聊天请求
            
        Yields:
            流式响应块
        """
        # 获取或创建会话
        session = None
        if request.session_id:
            session = self.get_session(db, request.session_id)
        
        if not session:
            session = self.create_session(db, SessionCreate(
                model=request.model,
                user_id=request.user_id
            ))
        
        # 构建消息
        if request.message:
            user_content = request.message
        elif request.messages:
            user_messages = [m for m in request.messages if m.role == MessageRole.USER]
            if user_messages:
                user_content = user_messages[-1].content
            else:
                raise ValueError("No user message provided")
        else:
            raise ValueError("Either 'message' or 'messages' must be provided")
        
        # 处理图片 OCR（如果有）
        ocr_context = ""
        if request.images:
            logger.info(f"Processing {len(request.images)} images with OCR...")
            ocr_context = await self._ocr_images(request.images)
            if ocr_context:
                logger.info(f"OCR extracted {len(ocr_context)} characters from images")
        
        # 如果有 OCR 结果，追加到用户消息中（不保存图片，只保存文字）
        message_to_save = user_content
        if ocr_context:
            user_content = f"{user_content}\n\n{ocr_context}"
        
        # 保存用户消息（除非跳过，用于重新生成场景）
        if not request.skip_save_user_message:
            self.add_message(db, str(session.id), "user", message_to_save)
        
        # 构建上下文（注意：这里会使用不含 OCR 的原始消息构建上下文）
        context_messages = self.build_context_messages(db, session)
        
        # 如果有 OCR 结果，替换最后一条用户消息的内容（加入 OCR）
        if ocr_context and context_messages:
            for i in range(len(context_messages) - 1, -1, -1):
                if context_messages[i].get("role") == "user":
                    context_messages[i]["content"] = user_content
                    break
        
        # 调用LLM
        temperature = request.temperature or float(session.temperature)
        max_tokens = request.max_tokens or session.max_tokens
        top_p = request.top_p or float(session.top_p)
        model = request.model or session.model
        
        # 收集完整响应
        full_content = ""
        full_reasoning = ""
        response_id = None
        created = int(time.time())
        finish_reason = None
        
        try:
            async for chunk in self.llm.async_stream_chat_completion(
                messages=context_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p
            ):
                response_id = chunk["id"]
                created = chunk["created"]
                
                if chunk["delta"].get("content"):
                    full_content += chunk["delta"]["content"]
                
                if chunk["delta"].get("reasoning_content"):
                    full_reasoning += chunk["delta"]["reasoning_content"]
                
                if chunk["finish_reason"]:
                    finish_reason = chunk["finish_reason"]
                
                yield {
                    "id": chunk["id"],
                    "object": "chat.completion.chunk",
                    "created": chunk["created"],
                    "model": chunk["model"],
                    # ... session_id ...
                    "session_id": str(session.id),
                    "choices": [{
                        "index": 0,
                        "delta": chunk["delta"],
                        "finish_reason": chunk["finish_reason"]
                    }]
                }
        except GeneratorExit:
            # Client disconnected
            logger.info(f"Stream interrupted for session {session.id}, saving partial content")
            finish_reason = "interrupted"
        except Exception as e:
            logger.error(f"Stream error for session {session.id}: {e}")
            finish_reason = "error"
        finally:
            # Save assistant message
            prompt_tokens = sum(self.llm.estimate_tokens(m["content"]) for m in context_messages)
            completion_tokens = self.llm.estimate_tokens(full_content) if full_content else 0
            
            extra_data = {}
            if full_reasoning:
                extra_data["reasoning"] = full_reasoning
            
            self.add_message(
                db,
                str(session.id),
                "assistant",
                full_content or "(No response generated)",
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                finish_reason=finish_reason or "unknown",
                extra_data=extra_data if extra_data else None
            )
            logger.info(f"Saved assistant message for session {session.id}, content length: {len(full_content)}")



# 全局聊天服务实例
chat_service = ChatService()
