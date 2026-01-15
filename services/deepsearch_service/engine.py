import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# 兼容本地和 Docker 环境的导入
try:
    from .prompts import QUERY_DECOMPOSITION_PROMPT, SUFFICIENCY_CHECK_PROMPT, REPORT_SYNTHESIS_PROMPT
except ImportError:
    from prompts import QUERY_DECOMPOSITION_PROMPT, SUFFICIENCY_CHECK_PROMPT, REPORT_SYNTHESIS_PROMPT

logger = logging.getLogger(__name__)

# ===== 搜索深度配置 =====
DEPTH_CONFIGS = {
    "quick": {
        "max_iterations": 1,
        "queries_per_iteration": 2,
        "max_results_per_query": 2,
        "sufficiency_threshold": 0.5,
        "max_report_tokens": 1000,
    },
    "normal": {
        "max_iterations": 3,
        "queries_per_iteration": 3,
        "max_results_per_query": 3,
        "sufficiency_threshold": 0.7,
        "max_report_tokens": 2000,
    },
    "deep": {
        "max_iterations": 5,
        "queries_per_iteration": 4,
        "max_results_per_query": 4,
        "sufficiency_threshold": 0.85,
        "max_report_tokens": 3000,
    },
}


# ===== Pydantic 模型 =====
class DeepSearchRequest(BaseModel):
    """深度搜索请求模型"""
    query: str = Field(..., description="用户问题", min_length=1, max_length=500)
    max_iterations: int = Field(3, description="最大迭代次数", ge=1, le=5)
    queries_per_iteration: int = Field(3, description="每轮生成的查询数", ge=1, le=5)
    depth_level: Literal["quick", "normal", "deep"] = Field("normal", description="搜索深度")


class SourceInfo(BaseModel):
    """来源信息"""
    title: str = Field(..., description="来源标题")
    url: str = Field(..., description="来源URL")
    relevance: float = Field(0.0, description="相关性评分")
    snippet: str = Field("", description="内容摘要")
    credibility: str = Field("unknown", description="可信度")


class SearchIteration(BaseModel):
    """单次搜索迭代记录"""
    iteration: int = Field(..., description="迭代次数")
    queries: List[str] = Field(..., description="本轮搜索的查询")
    results_count: int = Field(..., description="获取的结果数")
    new_results_count: int = Field(0, description="新增结果数（去重后）")
    key_findings: List[str] = Field(default_factory=list, description="关键发现")


class DeepSearchResponse(BaseModel):
    """深度搜索响应模型"""
    query: str = Field(..., description="原始问题")
    report: str = Field(..., description="综合分析报告")
    sources: List[SourceInfo] = Field(default_factory=list, description="信息来源列表")
    iterations: List[SearchIteration] = Field(default_factory=list, description="迭代记录")
    total_iterations: int = Field(..., description="总迭代次数")
    total_sources: int = Field(0, description="总来源数")
    depth_level: str = Field("normal", description="使用的搜索深度")
    elapsed_seconds: float = Field(0.0, description="耗时（秒）")
    search_timestamp: str = Field(..., description="搜索时间戳")


# ===== 深度搜索引擎 =====
class DeepSearchEngine:
    """迭代式深度搜索引擎（优化版）"""
    
    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    
    # 报告缓存配置
    CACHE_TTL_SECONDS = 1800  # 30 分钟
    CACHE_MAX_SIZE = 50  # 最多缓存 50 个报告
    
    def __init__(self):
        # LLM 配置
        self.llm_model = os.getenv("LLM_MODEL_NAME", "")
        self.llm_url = os.getenv("LLM_URL", "")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        
        if not self.llm_api_key:
            raise ValueError("LLM_API_KEY 未配置，请检查环境变量")
        
        self.llm_client = AsyncOpenAI(api_key=self.llm_api_key, base_url=self.llm_url)
        
        # WebSearch 服务配置
        self.websearch_host = os.getenv("SEARCH_SERVICE_HOST", "127.0.0.1")
        self.websearch_port = os.getenv("SEARCH_SERVICE_PORT", "8004")
        self.websearch_url = f"http://{self.websearch_host}:{self.websearch_port}"
        
        # 默认搜索配置（可被 depth_level 覆盖）
        self.max_iterations = int(os.getenv("DEEPSEARCH_MAX_ITERATIONS", "3"))
        self.queries_per_iteration = int(os.getenv("DEEPSEARCH_QUERIES_PER_ITERATION", "3"))
        
        # HTTP 客户端（连接池优化）
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),  # 减少超时，更快失败
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=15)  # 增加连接池
        )
        
        # LLM 并发限制（提高并发）
        self.llm_semaphore = asyncio.Semaphore(5)
        
        # WebSearch 健康状态
        self._websearch_healthy = True
        
        # 报告缓存：{cache_key: (timestamp, response)}
        self._report_cache: Dict[str, tuple] = {}
        
        # RAG 服务配置（通过 HTTP 调用 rag_service）
        self.rag_host = os.getenv("RAG_HOST", "rag_service")
        self.rag_port = os.getenv("RAG_SERVICE_PORT", "8008")
        self.rag_url = f"http://{self.rag_host}:{self.rag_port}"
        self._rag_enabled = False  # 启动后通过健康检查确认
        
        logger.info(f"DeepSearch 初始化完成 - LLM: {self.llm_model}, WebSearch: {self.websearch_url}, RAG: {self.rag_url}")
    
    def _get_cache_key(self, query: str, depth_level: str) -> str:
        """生成缓存 key"""
        return f"{query.strip().lower()}|{depth_level}"
    
    def _get_cached_report(self, query: str, depth_level: str) -> Optional[DeepSearchResponse]:
        """获取缓存的报告"""
        cache_key = self._get_cache_key(query, depth_level)
        cached = self._report_cache.get(cache_key)
        
        if cached:
            timestamp, response = cached
            age = (datetime.now() - timestamp).total_seconds()
            if age < self.CACHE_TTL_SECONDS:
                logger.info(f"报告缓存命中: '{query[:30]}...' (age: {age:.0f}s)")
                return response
            else:
                # 过期，删除
                del self._report_cache[cache_key]
        
        return None
    
    def _cache_report(self, query: str, depth_level: str, response: DeepSearchResponse):
        """缓存报告"""
        cache_key = self._get_cache_key(query, depth_level)
        
        # 如果缓存已满，删除最旧的
        if len(self._report_cache) >= self.CACHE_MAX_SIZE:
            oldest_key = min(self._report_cache, key=lambda k: self._report_cache[k][0])
            del self._report_cache[oldest_key]
        
        self._report_cache[cache_key] = (datetime.now(), response)
        logger.info(f"报告已缓存: '{query[:30]}...' (cache size: {len(self._report_cache)})")
    
    def _get_depth_config(self, depth_level: str) -> Dict[str, Any]:
        """获取搜索深度配置"""
        return DEPTH_CONFIGS.get(depth_level, DEPTH_CONFIGS["normal"])
    
    async def check_rag_health(self) -> bool:
        """检查 RAG 服务健康状态"""
        try:
            resp = await self.http_client.get(f"{self.rag_url}/health", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                self._rag_enabled = data.get("milvus_connected", False)
                return self._rag_enabled
        except Exception as e:
            logger.debug(f"RAG 健康检查失败: {e}")
        self._rag_enabled = False
        return False
    
    async def _rag_retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """RAG 检索：通过 rag_service 检索相关历史内容"""
        if not self._rag_enabled:
            return []
        
        try:
            resp = await self.http_client.post(
                f"{self.rag_url}/retrieve",
                json={
                    "query": query,
                    "top_k": top_k,
                    "min_score": 0.85,
                    "rerank": True
                },
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            
            results = data.get("results", [])
            if results:
                logger.info(f"RAG 检索到 {len(results)} 条相关历史内容 (query: '{query[:30]}...')")
            
            return [
                {
                    "text": r.get("text", ""),
                    "metadata": r.get("metadata", {}),
                    "score": r.get("score", 0)
                }
                for r in results
            ]
            
        except Exception as e:
            logger.warning(f"RAG 检索失败: {e}")
            return []
    
    async def check_websearch_health(self) -> bool:
        """检查 WebSearch 服务健康状态"""
        try:
            resp = await self.http_client.get(
                f"{self.websearch_url}/health",
                timeout=5.0
            )
            self._websearch_healthy = resp.status_code == 200
            return self._websearch_healthy
        except Exception as e:
            logger.warning(f"WebSearch 健康检查失败: {e}")
            self._websearch_healthy = False
            return False
    
    async def search(self, request: DeepSearchRequest) -> DeepSearchResponse:
        """执行深度搜索（优化版）"""
        # 0. 检查报告缓存
        cached_report = self._get_cached_report(request.query, request.depth_level)
        if cached_report:
            cached_report.search_timestamp = datetime.now().isoformat()
            cached_report.elapsed_seconds = 0.0
            return cached_report
        
        start_time = datetime.now()
        depth_config = self._get_depth_config(request.depth_level)
        
        logger.info(f"开始深度搜索: '{request.query}' [depth={request.depth_level}]")
        
        # 1. RAG 检索
        useful_context: List[Dict[str, Any]] = []
        rag_results = await self._rag_retrieve(request.query, top_k=5)
        if rag_results:
            for rag_item in rag_results:
                if rag_item.get("score", 0) >= 0.80:
                    useful_context.append({
                        "source": "RAG",
                        "title": rag_item.get("metadata", {}).get("title", "历史记录"),
                        "url": rag_item.get("metadata", {}).get("url", ""),
                        "content": rag_item.get("text", "")[:500],
                        "score": rag_item.get("score", 0)
                    })
            if useful_context:
                logger.info(f"RAG 预加载 {len(useful_context)} 条高质量历史内容")
        
        # 收集的信息
        collected_info: List[Dict[str, Any]] = []
        seen_urls: set = set()
        iterations: List[SearchIteration] = []
        all_sources: List[SourceInfo] = []
        missing_aspects: List[str] = []
        
        for ctx in useful_context:
            if ctx.get("url") and ctx["url"] not in seen_urls:
                seen_urls.add(ctx["url"])
                collected_info.append({
                    "title": ctx["title"],
                    "url": ctx["url"],
                    "content": ctx["content"],
                    "relevance_score": ctx["score"],
                    "from_rag": True
                })
        
        max_iter = min(request.max_iterations, depth_config["max_iterations"])
        queries_per_iter = min(request.queries_per_iteration, depth_config["queries_per_iteration"])
        max_results = depth_config["max_results_per_query"]
        sufficiency_threshold = depth_config["sufficiency_threshold"]
        
        for i in range(max_iter):
            iteration_num = i + 1
            logger.info(f"=== 迭代 {iteration_num}/{max_iter} ===")
            
            # 1. 生成查询
            queries = await self._generate_search_queries(
                request.query,
                collected_info,
                queries_per_iter,
                missing_aspects
            )
            logger.info(f"生成 {len(queries)} 个查询: {queries}")
            
            if not queries:
                logger.warning("未能生成有效查询，终止迭代")
                break
            
            # 2. 并行搜索
            search_results = await self._execute_searches_with_retry(queries, max_results)
            total_results = len(search_results)
            
            # 3. 去重
            new_count = 0
            for result in search_results:
                url = result.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    collected_info.append(result)
                    new_count += 1
                    
                    all_sources.append(SourceInfo(
                        title=result.get("title", ""),
                        url=url,
                        relevance=result.get("relevance_score", 0.0),
                        snippet=result.get("snippet", "")[:200],
                        credibility=result.get("credibility", "unknown")
                    ))
            
            logger.info(f"获取 {total_results} 条结果，新增 {new_count} 条")
            
            # 4. 评估充分性
            check_result = await self._check_sufficiency(request.query, collected_info)
            missing_aspects = check_result.get("missing_aspects", [])
            
            iterations.append(SearchIteration(
                iteration=iteration_num,
                queries=queries,
                results_count=total_results,
                new_results_count=new_count,
                key_findings=check_result.get("key_findings", [])
            ))
            
            confidence = check_result.get("confidence", 0)
            if check_result.get("sufficient", False) and confidence >= sufficiency_threshold:
                logger.info(f"信息已充分 (confidence: {confidence:.2f})")
                break
            
            if new_count == 0:
                logger.info("本轮无新增信息，终止迭代")
                break
            
        # 5. 生成报告
        valid_data = []
        seen_content_hashes = set()
        
        for item in collected_info:
            content = item.get("content", "").strip()
            if not content or len(content) < 50:
                continue
            content_hash = hashlib.md5(content[:200].encode()).hexdigest()
            if content_hash in seen_content_hashes:
                continue
            seen_content_hashes.add(content_hash)
            valid_data.append(item)
            
        logger.info(f"数据清洗: {len(collected_info)} -> {len(valid_data)} 条有效数据")

        report = await self._synthesize_report(
            request.query, 
            valid_data,
            depth_config["max_report_tokens"]
        )
        
        unique_sources = self._deduplicate_sources(all_sources)
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"深度搜索完成，耗时 {elapsed:.2f}s，{len(iterations)} 轮迭代")
        
        response = DeepSearchResponse(
            query=request.query,
            report=report,
            sources=unique_sources[:15],
            iterations=iterations,
            total_iterations=len(iterations),
            total_sources=len(unique_sources),
            depth_level=request.depth_level,
            elapsed_seconds=round(elapsed, 2),
            search_timestamp=datetime.now().isoformat()
        )
        
        self._cache_report(request.query, request.depth_level, response)
        
        return response
    
    async def _generate_search_queries(
        self, 
        query: str, 
        collected_info: List[Dict], 
        num_queries: int,
        missing_aspects: List[str]
    ) -> List[str]:
        """LLM 生成搜索查询"""
        try:
            info_summary = self._summarize_collected_info(collected_info, max_length=1500)
            missing_str = "、".join(missing_aspects) if missing_aspects else "（首次搜索，全面覆盖）"
            
            prompt = QUERY_DECOMPOSITION_PROMPT.format(
                query=query,
                collected_info=info_summary if info_summary else "（暂无）",
                missing_aspects=missing_str,
                num_queries=num_queries
            )
            
            result_text = await self._call_llm(prompt, max_tokens=500, temperature=0.7)
            result_text = self._clean_json_response(result_text)
            
            queries = json.loads(result_text)
            if isinstance(queries, list):
                return [q.strip() for q in queries if q and q.strip()][:num_queries]
            return []
        except Exception as e:
            logger.error(f"生成查询失败: {e}")
            return [query]
    
    async def _execute_searches_with_retry(
        self, 
        queries: List[str],
        max_results: int
    ) -> List[Dict[str, Any]]:
        """并行执行搜索"""
        tasks = [self._call_websearch_with_retry(q, max_results) for q in queries]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_results = []
        for i, result in enumerate(results_list):
            if isinstance(result, Exception):
                logger.warning(f"搜索 '{queries[i]}' 失败: {result}")
                continue
            if isinstance(result, list):
                all_results.extend(result)
        return all_results
    
    async def _call_websearch_with_retry(
        self, 
        query: str, 
        max_results: int
    ) -> List[Dict[str, Any]]:
        """调用 WebSearch 服务"""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self.http_client.post(
                    f"{self.websearch_url}/search",
                    json={"query": query, "max_results": max_results, "force_refresh": False},
                    timeout=90.0  # 增加超时以适应慢速抓取
                )
                response.raise_for_status()
                data = response.json()
                
                results = []
                for r in data.get("results", []):
                    if r.get("success") and r.get("data"):
                        results.append({
                            "query": query,
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("data", {}).get("title_summary", ""),
                            "content": r.get("data", {}).get("main_content", ""),
                            "key_info": r.get("data", {}).get("key_information", []),
                            "relevance_score": r.get("data", {}).get("relevance_score", 0.0),
                            "credibility": r.get("data", {}).get("credibility", "unknown")
                        })
                return results
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
        
        logger.error(f"WebSearch 调用失败: {last_error}")
        return []
    
    async def _check_sufficiency(
        self, 
        query: str, 
        collected_info: List[Dict]
    ) -> Dict[str, Any]:
        """评估信息充分性"""
        try:
            info_summary = self._summarize_collected_info(collected_info, max_length=2500)
            prompt = SUFFICIENCY_CHECK_PROMPT.format(
                query=query,
                collected_info=info_summary if info_summary else "（暂无）"
            )
            
            result_text = await self._call_llm(prompt, max_tokens=500, temperature=0.3)
            result_text = self._clean_json_response(result_text)
            
            return json.loads(result_text)
        except Exception as e:
            logger.error(f"充分性检查失败: {e}")
            return {
                "sufficient": False, "confidence": 0.0, 
                "missing_aspects": [], "key_findings": []
            }
    
    async def _synthesize_report(
        self, 
        query: str, 
        collected_info: List[Dict],
        max_tokens: int = 2000
    ) -> str:
        """生成综合报告"""
        try:
            info_summary = self._summarize_collected_info(collected_info, max_length=6000)
            min_words = max_tokens // 4
            max_words = max_tokens // 2
            
            prompt = REPORT_SYNTHESIS_PROMPT.format(
                query=query,
                collected_info=info_summary if info_summary else "（未收集到有效信息）",
                min_words=min_words,
                max_words=max_words
            )
            
            return await self._call_llm(prompt, max_tokens=max_tokens, temperature=0.5)
        except Exception as e:
            logger.error(f"报告生成失败: {e}")
            return f"## 报告生成失败\n\n错误信息: {str(e)}"
    
    async def _call_llm(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.5) -> str:
        async with self.llm_semaphore:
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
    
    def _summarize_collected_info(self, collected_info: List[Dict], max_length: int = 3000) -> str:
        if not collected_info:
            return ""
        
        parts = []
        current_length = 0
        sorted_info = sorted(collected_info, key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        for info in sorted_info:
            title = info.get("title", "未知来源")
            url = info.get("url", "")
            content = info.get("content", "")[:400]
            key_info = info.get("key_info", [])
            credibility = info.get("credibility", "unknown")
            
            try:
                domain = urlparse(url).netloc.replace("www.", "") if url else "未知"
            except Exception:
                domain = "未知"
            
            cred_mark = {"authoritative": "★权威", "commercial": "◆商业", "forum": "○社区"}.get(credibility, "")
            
            part = f"【{domain}】{title}"
            if cred_mark:
                part += f" ({cred_mark})"
            part += "\n"
            if content:
                part += f"{content}\n"
            if key_info:
                part += f"要点: {'; '.join(key_info[:3])}\n"
            part += "\n"
            
            if current_length + len(part) > max_length:
                break
            parts.append(part)
            current_length += len(part)
        
        return "".join(parts)
    
    def _deduplicate_sources(self, sources: List[SourceInfo]) -> List[SourceInfo]:
        seen_urls = set()
        unique = []
        for source in sources:
            if source.url and source.url not in seen_urls:
                seen_urls.add(source.url)
                unique.append(source)
        
        def sort_key(s):
            cred_score = {"authoritative": 1.0, "commercial": 0.5, "forum": 0.3}.get(s.credibility, 0.2)
            return (s.relevance * 0.7 + cred_score * 0.3)
        
        return sorted(unique, key=sort_key, reverse=True)
    
    @staticmethod
    def _clean_json_response(text: str) -> str:
        """清理 LLM 返回的 JSON 文本，支持多种格式"""
        text = text.strip()
        
        # 1. 移除 markdown 代码块标记
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # 2. 如果以有效 JSON 开头，直接返回
        if text.startswith("[") or text.startswith("{"):
            return text
        
        # 3. 尝试用正则提取 JSON 数组或对象
        json_array_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_array_match:
            return json_array_match.group()
        
        json_obj_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_obj_match:
            return json_obj_match.group()
        
        return text
    
    async def close(self):
        await self.http_client.aclose()
