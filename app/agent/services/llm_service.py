"""
LLM Service for Agent
Handles communication with LLM backend using OpenAI-compatible API
"""
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI, OpenAI

from ..config import settings

logger = logging.getLogger(__name__)


class AgentLLMService:
    """
    Agent 专用 LLM 服务
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
            api_key: API 密钥，默认从配置读取
            base_url: API 基础 URL，默认从配置读取
            model: 默认模型名称，默认从配置读取
        """
        self.api_key = api_key or settings.AGENT_LLM_API_KEY
        self.base_url = base_url or settings.AGENT_LLM_URL
        self.model = model or settings.AGENT_LLM_MODEL_NAME
        
        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None
        
        logger.info(f"Initialized AgentLLMService with model: {self.model}")
    
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
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 0.9,
        **kwargs
    ) -> Dict[str, Any]:
        """
        异步聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出 tokens
            top_p: Top-P 参数
            **kwargs: 其他参数
            
        Returns:
            完成响应
        """
        try:
            response = await self.async_client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                **kwargs
            )
            
            return {
                "content": response.choices[0].message.content,
                "finish_reason": response.choices[0].finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                },
                "model": response.model
            }
            
        except Exception as e:
            logger.error(f"LLM chat completion failed: {e}")
            raise
    
    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 0.9,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
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
        try:
            stream = await self.async_client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stream=True,
                **kwargs
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    yield {
                        "content": delta.content or "",
                        "finish_reason": chunk.choices[0].finish_reason
                    }
                    
        except Exception as e:
            logger.error(f"LLM stream chat completion failed: {e}")
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
            # AsyncOpenAI 没有 close 方法，设为 None 即可
            self._async_client = None
    
    def __del__(self):
        """析构时关闭连接"""
        self.close()


# 全局 LLM 服务实例
agent_llm_service = AgentLLMService()
