"""
LLM Service - OpenAI Compatible API Client
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
    LLM服务类
    封装与LLM后端的通信，支持同步和异步调用
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化LLM服务
        
        Args:
            api_key: API密钥，默认从配置读取（使用Chat专用配置）
            base_url: API基础URL，默认从配置读取（使用Chat专用配置）
            model: 默认模型名称，默认从配置读取（使用Chat专用配置）
        """
        # 使用Chat专用LLM配置
        self.api_key = api_key or settings.CHAT_LLM_API_KEY
        self.base_url = base_url or settings.CHAT_LLM_URL
        self.default_model = model or settings.CHAT_LLM_MODEL_NAME
        
        # 同步客户端
        self._sync_client: Optional[OpenAI] = None
        # 异步客户端
        self._async_client: Optional[AsyncOpenAI] = None
    
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
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        同步聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出tokens
            top_p: Top-P参数
            stream: 是否流式输出
            **kwargs: 其他参数
            
        Returns:
            聊天完成响应
        """
        model = model or self.default_model
        
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
            logger.info(f"Chat completion completed in {elapsed:.2f}s")
            
            if stream:
                return response  # 返回生成器
            
            # 解析响应
            choice = response.choices[0]
            usage = response.usage
            
            return {
                "id": response.id,
                "model": response.model,
                "content": choice.message.content,
                "role": choice.message.role,
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0
                },
                "created": response.created
            }
            
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise
    
    async def async_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        异步聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出tokens
            top_p: Top-P参数
            stream: 是否流式输出
            **kwargs: 其他参数
            
        Returns:
            聊天完成响应
        """
        model = model or self.default_model
        
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
            logger.info(f"Async chat completion completed in {elapsed:.2f}s")
            
            if stream:
                return response  # 返回异步生成器
            
            # 解析响应
            choice = response.choices[0]
            usage = response.usage
            
            return {
                "id": response.id,
                "model": response.model,
                "content": choice.message.content,
                "role": choice.message.role,
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0
                },
                "created": response.created
            }
            
        except Exception as e:
            logger.error(f"Async chat completion error: {e}")
            raise
    
    async def async_stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        异步流式聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出tokens
            top_p: Top-P参数
            **kwargs: 其他参数
            
        Yields:
            流式响应块
        """
        model = model or self.default_model
        
        try:
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
                if chunk.choices:
                    choice = chunk.choices[0]
                    delta = choice.delta
                    
                    yield {
                        "id": chunk.id,
                        "model": chunk.model,
                        "delta": {
                            "role": delta.role if delta.role else None,
                            "content": delta.content if delta.content else "",
                            "reasoning_content": getattr(delta, "reasoning_content", None)
                        },

                        "finish_reason": choice.finish_reason,
                        "created": chunk.created
                    }
                    
        except Exception as e:
            logger.error(f"Async stream chat completion error: {e}")
            raise
    
    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的token数量
        简单估算：中文约1.5字符/token，英文约4字符/token
        
        Args:
            text: 输入文本
            
        Returns:
            估算的token数量
        """
        # 简单估算
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        # 中文约1.5字符/token，英文约4字符/token
        estimated = int(chinese_chars / 1.5 + other_chars / 4)
        return max(1, estimated)
    
    def close(self):
        """关闭客户端连接"""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
        if self._async_client:
            # 异步客户端需要在异步上下文中关闭
            pass
    
    def __del__(self):
        """析构时关闭连接"""
        self.close()


# 全局LLM服务实例
llm_service = LLMService()
