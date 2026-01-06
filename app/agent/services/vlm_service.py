"""
Image Analysis Service for Agent
Uses OCR + LLM to replace VLM for image understanding and content extraction
"""
import base64
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI

from ..config import settings

logger = logging.getLogger(__name__)

# OCR 客户端
try:
    from services.ocr_service.client import OCRServiceClient
except ImportError:
    import sys
    sys.path.insert(0, '/app')
    from services.ocr_service.client import OCRServiceClient


class VLMService:
    """
    图片分析服务（OCR + LLM 替代 VLM）
    
    用于：
    1. 理解用户输入的图片
    2. 结合用户文本信息提取图片中的有用内容
    3. 多模态内容分析
    
    注意：类名保留 VLMService 以保持向后兼容
    """
    
    # 图片理解的默认提示词
    DEFAULT_IMAGE_ANALYSIS_PROMPT = """请根据 OCR 识别出的图片文字内容，结合用户的问题或需求，分析并提取有用的信息。

【OCR 识别文本】
{ocr_text}

请按以下格式返回分析结果：

## 内容概述
简要描述图片的主要内容

## 关键信息
列出图片中的关键信息点，包括：
- 文字内容
- 数据/数字（如有）
- 重要元素

## 与用户需求相关的内容
根据用户的问题，提取最相关的信息

## 补充观察
其他可能有价值的信息
"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化图片分析服务
        
        Args:
            api_key: API 密钥，默认从环境变量读取
            base_url: API 基础 URL
            model: LLM 模型名称
        """
        # 使用普通 LLM 配置
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = base_url or settings.LLM_URL
        self.model = model or settings.LLM_MODEL_NAME
        
        self._async_client: Optional[AsyncOpenAI] = None
        
        # OCR 客户端
        import os
        ocr_host = os.getenv("OCR_HOST", "ocr_service")
        ocr_port = os.getenv("OCR_PORT", "8001")
        self.ocr_client = OCRServiceClient(base_url=f"http://{ocr_host}:{ocr_port}")
        self.ocr_executor = ThreadPoolExecutor(max_workers=3)
        
        logger.info(f"Initialized ImageAnalysisService with model: {self.model}")
    
    @property
    def async_client(self) -> AsyncOpenAI:
        """获取异步客户端（懒加载）"""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        return self._async_client
    
    def _encode_image_to_base64(self, image_path: Union[str, Path]) -> str:
        """将本地图片编码为 base64"""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _ocr_image_sync(self, image_base64: str) -> str:
        """同步 OCR 识别图片"""
        try:
            ocr_result = self.ocr_client.ocr(image_base64)
            
            # 提取 OCR 文本
            if isinstance(ocr_result, list):
                texts = []
                for item in ocr_result:
                    if isinstance(item, dict) and 'text' in item:
                        texts.append(item['text'])
                    elif isinstance(item, list) and len(item) > 1:
                        if isinstance(item[1], tuple):
                            texts.append(item[1][0])
                    elif isinstance(item, str):
                        texts.append(item)
                return "\n".join(texts)
            elif isinstance(ocr_result, dict):
                return ocr_result.get('text', str(ocr_result))
            else:
                return str(ocr_result)
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return ""
    
    async def _ocr_image(self, image_base64: str) -> str:
        """异步 OCR 识别图片"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.ocr_executor,
            self._ocr_image_sync,
            image_base64
        )
    
    async def _get_images_text(
        self,
        images: List[Union[str, Dict[str, str]]]
    ) -> str:
        """
        从图片列表中提取文本
        
        Args:
            images: 图片列表（URL、本地路径或 base64）
                
        Returns:
            合并的 OCR 文本
        """
        all_texts = []
        
        for i, img in enumerate(images, 1):
            try:
                image_base64 = None
                
                if isinstance(img, str):
                    if img.startswith(("http://", "https://")):
                        # URL - 需要下载后 OCR
                        import httpx
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(img, timeout=10)
                            image_base64 = base64.b64encode(resp.content).decode("utf-8")
                    elif img.startswith("data:"):
                        # data URL
                        image_base64 = img.split(",", 1)[1] if "," in img else img
                    else:
                        # 本地文件
                        image_base64 = self._encode_image_to_base64(img)
                elif isinstance(img, dict):
                    if img.get("type") == "base64":
                        image_base64 = img.get("data")
                    elif img.get("type") == "url":
                        import httpx
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(img["url"], timeout=10)
                            image_base64 = base64.b64encode(resp.content).decode("utf-8")
                
                if image_base64:
                    text = await self._ocr_image(image_base64)
                    if text:
                        all_texts.append(f"【图片 {i}】\n{text}")
            except Exception as e:
                logger.warning(f"Failed to process image {i}: {e}")
                all_texts.append(f"【图片 {i}】（处理失败）")
        
        return "\n\n".join(all_texts) if all_texts else "（未能识别到图片文字）"
    
    async def analyze_image(
        self,
        images: List[Union[str, Dict[str, str]]],
        user_message: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """
        分析图片内容（使用 OCR + LLM）
        
        Args:
            images: 图片列表（URL、本地路径或 base64）
            user_message: 用户的问题或需求
            custom_prompt: 自定义分析提示词
            temperature: 温度参数
            max_tokens: 最大输出 tokens
            
        Returns:
            分析结果
        """
        try:
            # 1. OCR 提取图片文字
            ocr_text = await self._get_images_text(images)
            
            # 2. 构建提示词
            if custom_prompt:
                prompt = custom_prompt.format(ocr_text=ocr_text)
            else:
                prompt = self.DEFAULT_IMAGE_ANALYSIS_PROMPT.format(ocr_text=ocr_text)
            
            # 如果有用户消息，添加到提示词中
            if user_message:
                prompt = f"用户需求/问题：{user_message}\n\n{prompt}"
            
            # 3. 调用 LLM（纯文本）
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            analysis = response.choices[0].message.content
            
            return {
                "success": True,
                "analysis": analysis,
                "ocr_text": ocr_text,
                "model": self.model,
                "images_count": len(images),
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "analysis": None
            }
    
    async def extract_information(
        self,
        images: List[Union[str, Dict[str, str]]],
        user_context: str,
        extraction_focus: Optional[List[str]] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """
        从图片中提取特定信息（使用 OCR + LLM）
        
        Args:
            images: 图片列表
            user_context: 用户上下文信息
            extraction_focus: 重点提取的内容类型列表
            temperature: 温度参数
            max_tokens: 最大输出 tokens
            
        Returns:
            提取结果（JSON 格式）
        """
        try:
            # 1. OCR 提取图片文字
            ocr_text = await self._get_images_text(images)
            
            focus_text = ""
            if extraction_focus:
                focus_text = f"\n重点关注以下类型的信息：\n" + "\n".join(f"- {f}" for f in extraction_focus)
            
            prompt = f"""请分析 OCR 识别出的图片文字内容，结合以下用户上下文信息，提取有价值的内容。

用户上下文：{user_context}
{focus_text}

【OCR 识别文本】
{ocr_text}

请以 JSON 格式返回提取结果：
```json
{{
    "summary": "图片内容摘要",
    "extracted_text": ["提取的文字内容列表"],
    "key_data": {{"关键数据名": "数值或内容"}},
    "relevant_info": ["与用户需求相关的信息点"],
    "entities": ["识别到的实体（人名、地名、品牌等）"],
    "suggestions": ["基于图片内容的建议或见解"]
}}
```

只返回 JSON，不要包含其他解释。"""
            
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            result_text = response.choices[0].message.content
            
            # 尝试解析 JSON
            json_match = re.search(r"```json\s*(.*?)\s*```", result_text, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group(1))
            else:
                # 尝试直接解析
                extracted = json.loads(result_text)
            
            return {
                "success": True,
                "extracted": extracted,
                "ocr_text": ocr_text,
                "raw_response": result_text,
                "model": self.model
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return {
                "success": True,
                "extracted": None,
                "ocr_text": ocr_text,
                "raw_response": result_text,
                "parse_error": str(e)
            }
        except Exception as e:
            logger.error(f"Image extraction failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def understand_with_context(
        self,
        images: List[Union[str, Dict[str, str]]],
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.5,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """
        结合对话上下文理解图片（使用 OCR + LLM）
        
        Args:
            images: 图片列表
            user_message: 用户当前消息
            conversation_history: 对话历史
            temperature: 温度参数
            max_tokens: 最大输出 tokens
            
        Returns:
            理解结果
        """
        try:
            # 1. OCR 提取图片文字
            ocr_text = await self._get_images_text(images)
            
            messages = []
            
            # 添加系统提示
            messages.append({
                "role": "system",
                "content": """你是一个智能 AI 助手，能够理解图片中的文字内容并结合用户需求提供帮助。
请仔细分析 OCR 识别出的图片文字，理解其内容，并结合用户的问题给出有价值的回答。
如果图片中包含重要的文字、数据或其他信息，请务必提取并引用。"""
            })
            
            # 添加对话历史
            if conversation_history:
                for msg in conversation_history[-5:]:  # 最多5条历史
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            # 添加当前消息（包含 OCR 文本）
            user_content = f"""{user_message}

【图片 OCR 识别结果】
{ocr_text}"""
            
            messages.append({
                "role": "user",
                "content": user_content
            })
            
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return {
                "success": True,
                "response": response.choices[0].message.content,
                "ocr_text": ocr_text,
                "model": self.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Image context understanding failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def close(self):
        """关闭客户端连接"""
        if self._async_client:
            self._async_client = None
        if self.ocr_executor:
            self.ocr_executor.shutdown(wait=False)


# 全局服务实例（保持向后兼容）
vlm_service = VLMService()
