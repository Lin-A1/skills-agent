"""
LLM Service - OpenAI Compatible API Client for Agent
Handles communication with LLM backends
"""
import logging
from typing import List, Dict, Any, AsyncGenerator, Optional
from openai import OpenAI, AsyncOpenAI
import time

from ..config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    LLM 服务类
    封装与 LLM 后端的通信，支持同步和异步调用
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化 LLM 服务
        
        Args:
            api_key: API 密钥，默认从配置读取（使用 Agent 专用配置）
            base_url: API 基础 URL，默认从配置读取（使用 Agent 专用配置）
            model: 默认模型名称，默认从配置读取（使用 Agent 专用配置）
        """
        self.api_key = api_key or settings.AGENT_LLM_API_KEY
        self.base_url = base_url or settings.AGENT_LLM_URL
        self.model = model or settings.AGENT_LLM_MODEL_NAME
        
        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None
        
        logger.info(f"LLMService initialized with model: {self.model}")

    @property
    def sync_client(self) -> OpenAI:
        """获取同步客户端（懒加载）"""
        if self._sync_client is None:
            self._sync_client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        return self._sync_client

    @property
    def async_client(self) -> AsyncOpenAI:
        """获取异步客户端（懒加载）"""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        return self._async_client

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        top_p: float = 0.9,
        stream: bool = False,
        **kwargs
    ) -> Any:
        """
        同步聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出 tokens
            top_p: Top-P 参数
            stream: 是否流式输出
            **kwargs: 其他参数
            
        Returns:
            LLM 响应对象
        """
        model = model or self.model
        
        logger.debug(f"Sync chat completion: model={model}, messages={len(messages)}")
        
        try:
            start_time = time.time()
            response = self.sync_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stream=stream,
                **kwargs
            )
            elapsed = time.time() - start_time
            logger.debug(f"Chat completion took {elapsed:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise

    async def async_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        top_p: float = 0.9,
        stream: bool = False,
        **kwargs
    ) -> Any:
        """
        异步聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出 tokens
            top_p: Top-P 参数
            stream: 是否流式输出
            **kwargs: 其他参数
            
        Returns:
            LLM 响应对象
        """
        model = model or self.model
        
        logger.debug(f"Async chat completion: model={model}, messages={len(messages)}")
        
        try:
            start_time = time.time()
            response = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stream=stream,
                **kwargs
            )
            elapsed = time.time() - start_time
            logger.debug(f"Async chat completion took {elapsed:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"Async chat completion error: {e}")
            raise

    async def async_stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        top_p: float = 0.9,
        **kwargs
    ) -> AsyncGenerator[Any, None]:
        """
        异步流式聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出 tokens
            top_p: Top-P 参数
            **kwargs: 其他参数
            
        Yields:
            流式响应块
        """
        model = model or self.model
        
        logger.debug(f"Stream chat completion: model={model}, messages={len(messages)}")
        
        try:
            start_time = time.time()
            stream = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stream=True,
                **kwargs
            )
            
            async for chunk in stream:
                yield chunk
            
            elapsed = time.time() - start_time
            logger.debug(f"Stream chat completion took {elapsed:.2f}s")
            
        except Exception as e:
            logger.error(f"Stream chat completion error: {e}")
            raise

    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数量
        简单估算：中文约 1.5 字符/token，英文约 4 字符/token
        
        Args:
            text: 输入文本
            
        Returns:
            估算的 token 数量
        """
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    def close(self):
        """关闭客户端连接"""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
        if self._async_client:
            # AsyncOpenAI 没有 close 方法
            self._async_client = None

    def __del__(self):
        """析构时关闭连接"""
        self.close()


# 全局 LLM 服务实例
llm_service = LLMService()
