"""
内容分析模块

职责：
- OCR 文本提取
- LLM 内容分析
- JSON 响应清理
- 结果验证
- 分析重试与降级处理

从 analyzer.py 提取，遵循单一职责原则。
"""
import asyncio
import base64
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from openai import AsyncOpenAI

from .models import VLMAnalysisData

logger = logging.getLogger(__name__)


class ContentAnalyzer:
    """内容分析器（OCR + LLM）"""
    
    # LLM 分析提示词模板
    LLM_ANALYSIS_PROMPT_TEMPLATE = """你是专业的网页内容分析助手，负责为联网搜索工具提取**可操作的实用信息**。

        【核心原则】
        ⚠️ 重要：用户搜索是为了解决问题，不是了解网站。请：
        1. 提取能直接回答用户问题的内容（步骤、方法、解决方案）
        2. 忽略网站介绍、公司简介、产品宣传等无关内容
        3. 如果页面只有介绍性内容而无实质信息，给低分（0.3以下）

        【任务】分析网页文本，提取与搜索词相关的**可操作信息**
        【搜索词】{query}

        【页面文本内容】
        {extracted_text}

        【OCR 识别文本】
        {ocr_text}

        请严格按JSON格式返回结果：

        {{
            "title_summary": "页面主题概括",
            "main_content": "核心内容详述",
            "key_information": ["要点1", "要点2", "要点3"],
            "credibility": "authoritative",
            "relevance_score": 0.85,
            "cacheable": true
        }}

        【字段说明】

        1. title_summary (20-60字)
        - 概括页面能解决什么问题
        - 格式建议：「如何XXX的方法/步骤/教程」

        2. main_content (300-500字) ⭐ 最重要
        - 如果是教程/指南：提取完整的操作步骤（第一步...第二步...）
        - 如果是问答：提取具体的解决方案
        - 如果是文档：提取关键配置/代码/命令
        - ⚠️ 不要写：「本文介绍了...」「该网站提供...」等介绍性语句
        - ✅ 直接写：具体的操作步骤、命令、配置方法

        3. key_information (3-6条结构化要点)
        - 每条是一个可独立使用的知识点
        - 优先提取：
          * 具体步骤（如：「步骤1：打开设置 → 账户管理 → 绑定」）
          * 命令/代码（如：「命令：ssh-keygen -t ed25519」）
          * 注意事项（如：「注意：需要先安装 Git」）
          * 常见问题解决（如：「如果报错XXX，解决方法是...」）

        4. credibility (来源可信度)
        - authoritative: 官方文档、技术博客、知名平台
        - commercial: 产品页面、营销内容
        - forum: 论坛、问答、个人博客
        - unknown: 无法判断

        5. relevance_score (0.0-1.0 相关性评分)
        - 0.9-1.0: 直接提供完整的操作步骤/解决方案
        - 0.7-0.9: 包含关键信息，但不够完整
        - 0.5-0.7: 部分相关，有参考价值
        - 0.3-0.5: 只有少量相关信息
        - 0.0-0.3: 不相关/只有介绍没有实质内容

        6. cacheable (是否适合缓存)
        - true: 教程、文档、配置方法
        - false: 新闻、动态信息、价格

        【低分情况】给0.3以下：
        - ❌ 页面只介绍网站/产品功能，没有具体操作方法
        - ❌ 内容是「XXX是什么」但用户问的是「怎么做」
        - ❌ 广告页、登录页、错误页
        - ❌ 内容过于碎片化

        【输出规范】仅输出JSON，禁止任何其他文字"""

    def __init__(
        self,
        llm_client: AsyncOpenAI,
        ocr_client,
        llm_model: str = "qwen-plus",
        llm_max_tokens: int = 1500,
        llm_temperature: float = 0.3,
        llm_timeout: float = 60.0,
        max_retry_count: int = 1,
        min_content_length: int = 150,
        min_key_info_count: int = 2,
        min_relevance_score: float = 0.5
    ):
        self.llm_client = llm_client
        self.ocr_client = ocr_client
        self.llm_model = llm_model
        self.llm_max_tokens = llm_max_tokens
        self.llm_temperature = llm_temperature
        self.llm_timeout = llm_timeout
        self.max_retry_count = max_retry_count
        self.min_content_length = min_content_length
        self.min_key_info_count = min_key_info_count
        self.min_relevance_score = min_relevance_score
        
        self.llm_semaphore = asyncio.Semaphore(5)
        self.ocr_executor = ThreadPoolExecutor(max_workers=3)
    
    async def analyze(
        self,
        image_bytes: bytes,
        query: str,
        title: str,
        url: str,
        extracted_text: dict
    ) -> Optional[VLMAnalysisData]:
        """带重试的 OCR + LLM 分析"""
        result = None
        for attempt in range(self.max_retry_count + 1):
            result = await self._analyze_with_ocr_llm(
                image_bytes, query, title, url, extracted_text
            )
            if result and self._validate_result(result):
                return result
            if attempt < self.max_retry_count:
                await asyncio.sleep(0.5)
        return result
    
    def _validate_result(self, data: VLMAnalysisData) -> bool:
        """验证分析结果质量"""
        if not data:
            return False
        if len(data.main_content) < self.min_content_length:
            return False
        if len(data.key_information) < self.min_key_info_count:
            return False
        if data.relevance_score < self.min_relevance_score:
            return False
        return True
    
    async def _ocr_image(self, image_bytes: bytes) -> str:
        """异步调用 OCR 服务提取图片文本"""
        try:
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            loop = asyncio.get_event_loop()
            ocr_result = await loop.run_in_executor(
                self.ocr_executor,
                self.ocr_client.ocr,
                image_base64
            )
            
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
            logger.warning(f"OCR 提取失败: {e}")
            return ""
    
    async def _analyze_with_ocr_llm(
        self,
        image_bytes: bytes,
        query: str,
        title: str,
        url: str,
        extracted_text: dict
    ) -> Optional[VLMAnalysisData]:
        """使用 OCR + LLM 分析截图"""
        try:
            # 1. OCR 提取截图中的文本
            ocr_text = await self._ocr_image(image_bytes)
            
            # 2. 构建页面文本摘要
            text_summary = self._build_text_summary(extracted_text)
            
            # 3. 构建 LLM 提示词
            ocr_text_summary = ocr_text[:800] if ocr_text else "（OCR 未提取到文本）"
            text_for_prompt = text_summary[:1000]
            
            prompt = self.LLM_ANALYSIS_PROMPT_TEMPLATE.format(
                query=query, 
                extracted_text=text_for_prompt,
                ocr_text=ocr_text_summary
            )

            # 4. 调用 LLM
            async with self.llm_semaphore:
                try:
                    response = await asyncio.wait_for(
                        self.llm_client.chat.completions.create(
                            model=self.llm_model,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=self.llm_max_tokens,
                            timeout=45.0
                        ),
                        timeout=50.0
                    )
                    
                    result_text = response.choices[0].message.content.strip()
                    result_text = self._clean_json_response(result_text)
                    data = json.loads(result_text)
                    
                    return self._normalize_result(data)

                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"LLM 分析失败或超时 ({str(e)})，启用降级处理: {url}")
                    return self._fallback_result(title, extracted_text, query)

        except Exception as e:
            logger.error(f"分析流程严重错误: {e}")
            return None
    
    def _build_text_summary(self, extracted_text: dict) -> str:
        """构建页面文本摘要"""
        if not extracted_text:
            return "（未提取到文本）"
        
        parts = []
        if extracted_text.get("title"):
            parts.append(f"标题: {extracted_text['title']}")
        if extracted_text.get("h1"):
            parts.append(f"主标题: {extracted_text['h1']}")
        if extracted_text.get("meta_description"):
            parts.append(f"描述: {extracted_text['meta_description']}")
        if extracted_text.get("main_text"):
            parts.append(f"正文摘要: {extracted_text['main_text'][:1500]}")
        
        return "\n".join(parts) if parts else "（未提取到文本）"
    
    def _normalize_result(self, data: dict) -> Optional[VLMAnalysisData]:
        """规范化 LLM 返回的结果"""
        required_fields = ['title_summary', 'main_content', 'key_information', 'credibility', 'relevance_score']
        if any(f not in data for f in required_fields):
            logger.warning("LLM 返回数据缺少必要字段，使用降级方案")
            return None
        
        # 规范化处理
        if len(data['title_summary']) > 100:
            data['title_summary'] = data['title_summary'][:97] + "..."
        if len(data['main_content']) > 500:
            data['main_content'] = data['main_content'][:497] + "..."
        
        if isinstance(data['key_information'], str):
            data['key_information'] = [data['key_information']]
        elif not isinstance(data['key_information'], list):
            data['key_information'] = []
        data['key_information'] = [str(item)[:200] for item in data['key_information'][:8]]
        if not data['key_information']:
            data['key_information'] = [data['title_summary'][:100]]
        
        valid_credibility = ['authoritative', 'commercial', 'forum', 'unknown']
        if data['credibility'] not in valid_credibility:
            data['credibility'] = 'unknown'
        
        try:
            data['relevance_score'] = float(data['relevance_score'])
            data['relevance_score'] = max(0.0, min(1.0, data['relevance_score']))
        except (ValueError, TypeError):
            data['relevance_score'] = 0.5
            
        if 'cacheable' not in data:
            data['cacheable'] = True
            
        return VLMAnalysisData(**data)
    
    def _fallback_result(
        self, 
        title: str, 
        extracted_text: dict, 
        query: str
    ) -> VLMAnalysisData:
        """降级处理：当 LLM 失败时构建基础结果"""
        fallback_summary = extracted_text.get("meta_description", "")
        if not fallback_summary:
            main_text = extracted_text.get("main_text", "")
            fallback_summary = main_text[:150] + "..." if main_text else title
        
        # 简单的关键词匹配计算相关度
        fallback_score = 0.6
        query_terms = query.lower().split()
        content_lower = (extracted_text.get("main_text", "") + title).lower()
        match_count = sum(1 for term in query_terms if term in content_lower)
        if match_count > 0:
            fallback_score += min(0.3, match_count * 0.1)
        
        return VLMAnalysisData(
            title_summary=title[:100],
            main_content=f"【自动摘要】（智能分析超时，显示原始内容）\n{fallback_summary}",
            key_information=["由于网络原因，智能分析未能完成", "已为您保留原始页面链接和摘要"],
            credibility="unknown",
            relevance_score=fallback_score,
            cacheable=False
        )
    
    @staticmethod
    def _clean_json_response(text: str) -> str:
        """清理 LLM 返回的 JSON 文本"""
        # 移除 markdown 代码块标记
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # 移除控制字符
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # 修复末尾多余的逗号
        text = re.sub(r',\s*]', ']', text)
        text = re.sub(r',\s*}', '}', text)
        
        # 提取第一个完整的 JSON 对象
        brace_count = 0
        start_idx = -1
        end_idx = -1
        for i, char in enumerate(text):
            if char == '{':
                if start_idx == -1:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx != -1:
                    end_idx = i + 1
                    break
        
        if start_idx != -1 and end_idx != -1:
            text = text[start_idx:end_idx]
        
        return text.strip()
    
    def close(self):
        """清理资源"""
        self.ocr_executor.shutdown(wait=False)
