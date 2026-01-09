"""
联网搜索分析器 (门面类)

职责：
- 协调搜索流程
- 组合子模块完成任务
- 管理缓存层

重构后从 1000+ 行精简为门面类，核心逻辑委托给：
- URLScorer: URL 质量评分
- PageFetcher: 页面获取
- ContentAnalyzer: 内容分析
- ResultFilter: 结果过滤
"""
import asyncio
import logging
import os
import random
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from .models import VLMAnalysisData, SearchResult
from .browser_pool import BrowserPool
from .storage_clients import SearchCacheManager, VectorCacheManager
from .url_scorer import URLScorer
from .page_fetcher import PageFetcher
from .content_analyzer import ContentAnalyzer
from .result_filter import ResultFilter

# OCR 客户端导入（兼容容器和本地环境）
try:
    from services.ocr_service.client import OCRServiceClient
except ImportError:
    try:
        from ocr_service.client import OCRServiceClient
    except ImportError:
        import sys
        sys.path.insert(0, '/app')
        from services.ocr_service.client import OCRServiceClient

# Rerank 客户端导入
try:
    from services.rerank_service.client import RerankServiceClient
except ImportError:
    try:
        from rerank_service.client import RerankServiceClient
    except ImportError:
        import sys
        sys.path.insert(0, '/app')
        from services.rerank_service.client import RerankServiceClient

logger = logging.getLogger(__name__)


class IntelligentSearchAnalyzer:
    """联网搜索分析器（门面类）"""

    def __init__(
        self,
        browser_pool: BrowserPool,
        cache_manager: SearchCacheManager,
        vector_cache_manager: Optional[VectorCacheManager] = None
    ):
        # === LLM 配置 ===
        self.llm_model = os.getenv("LLM_MODEL_NAME", "qwen-plus")
        self.llm_url = os.getenv("LLM_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        
        if not self.llm_api_key:
            raise ValueError("LLM_API_KEY 未配置，请检查环境变量")

        # === SearXNG 配置 ===
        self.searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8005")
        self.searxng_timeout = float(os.getenv("SEARXNG_TIMEOUT", "10.0"))
        self.searxng_engines = os.getenv("SEARXNG_ENGINES", "bing,baidu,360search")
        self.searxng_language = os.getenv("SEARXNG_LANGUAGE", "zh-CN")
        self.enable_baike = os.getenv("ENABLE_BAIKE_SEARCH", "true").lower() == "true"

        # === 外部依赖 ===
        self.browser_pool = browser_pool
        self.cache_manager = cache_manager
        self.vector_cache_manager = vector_cache_manager
        
        # === 初始化子模块 ===
        self.url_scorer = URLScorer()
        self.page_fetcher = PageFetcher()
        self.result_filter = ResultFilter()
        
        # OCR 客户端
        ocr_host = os.getenv("OCR_HOST", "ocr_service")
        ocr_port = os.getenv("OCR_PORT", "8001")
        ocr_client = OCRServiceClient(base_url=f"http://{ocr_host}:{ocr_port}")

        # Rerank 客户端
        self.rerank_client = RerankServiceClient()

        # LLM 客户端
        
        # LLM 客户端
        llm_client = AsyncOpenAI(api_key=self.llm_api_key, base_url=self.llm_url)
        
        self.content_analyzer = ContentAnalyzer(
            llm_client=llm_client,
            ocr_client=ocr_client,
            llm_model=self.llm_model
        )
        
        # HTTP 客户端
        self.http_client = httpx.AsyncClient(
            timeout=self.searxng_timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )
        
        # 并发配置
        self.max_concurrent_pages = 4

        logger.info(
            f"初始化完成 - LLM模型: {self.llm_model}, "
            f"OCR: {ocr_host}:{ocr_port}, 并发: {self.max_concurrent_pages}页面"
        )

    async def search(
        self,
        query: str,
        max_results: int = 5,
        force_refresh: bool = False
    ) -> tuple[List[SearchResult], int]:
        """
        执行搜索并分析
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数量
            force_refresh: 是否强制刷新（忽略缓存）
            
        Returns:
            (搜索结果列表, 缓存命中数量)
        """
        search_start_time = datetime.now()
        logger.info(f"开始搜索: '{query}' (最多 {max_results} 个结果, 强制刷新: {force_refresh})")
        
        cached_results = []
        cached_count = 0
        
        # 1. 检查缓存
        if not force_refresh:
            cached_results, cached_count = await self._fetch_from_cache(query, max_results)
            if cached_count >= max_results:
                logger.info(f"缓存完全命中: {cached_count} 条结果")
                return cached_results, cached_count
            logger.info(f"缓存部分命中: {cached_count} 条，需补充 {max_results - cached_count} 条")
        
        # 2. 从网络获取新结果
        need_count = max_results - cached_count
        new_results = await self._fetch_from_web(query, need_count, cached_results)
        
        # 3. 后台保存缓存
        if new_results:
            asyncio.create_task(self._save_to_caches(query, new_results))
        
        # 4. 合并和过滤结果
        all_results = cached_results + new_results
        final_results = self.result_filter.process(all_results, max_results)
        
        # 5. 统计和日志
        success_count = sum(1 for r in final_results if r.success)
        elapsed = (datetime.now() - search_start_time).total_seconds()
        logger.info(
            f"搜索完成: 成功 {success_count}/{len(final_results)} 个, "
            f"缓存 {cached_count} 个, 耗时 {elapsed:.2f}s"
        )
        
        return final_results, cached_count

    async def _fetch_from_cache(
        self,
        query: str,
        max_results: int
    ) -> tuple[List[SearchResult], int]:
        """从缓存获取结果"""
        cached_results = []
        
        # 尝试向量语义搜索
        if self.vector_cache_manager and self.vector_cache_manager.is_available:
            try:
                logger.info(f"执行向量语义搜索: {query}")
                vector_hits = self.vector_cache_manager.semantic_search(
                    query, top_k=max_results, min_score=0.90, rerank=True
                )
                
                if vector_hits:
                    logger.info(f"向量缓存命中: 找到 {len(vector_hits)} 个高相似度结果")
                    for i, hit in enumerate(vector_hits):
                        cached_results.append(self._convert_vector_hit(hit, i + 1))
            except Exception as e:
                logger.warning(f"向量缓存查询失败: {e}")

        # 普通数据库缓存补充
        if len(cached_results) < max_results and self.cache_manager.is_available:
            keyword_results = self.cache_manager.search_cache(query, max_results)
            existing_urls = {r.url for r in cached_results}
            for res in keyword_results:
                if res.url not in existing_urls:
                    cached_results.append(res)
                    existing_urls.add(res.url)
        
        cached_results = cached_results[:max_results]
        return cached_results, len(cached_results)

    def _convert_vector_hit(self, hit: dict, index: int) -> SearchResult:
        """将向量搜索结果转换为 SearchResult"""
        meta = hit.get("metadata", {})
        content = hit.get("text", "")
        parts = content.split("\n", 1)
        title = meta.get("title") or (parts[0] if parts else "")
        main_content = parts[1] if len(parts) > 1 else content
        
        vlm_data = VLMAnalysisData(
            title_summary=title[:100],
            main_content=main_content[:500],
            key_information=meta.get("key_information", []),
            credibility=meta.get("credibility", "unknown"),
            relevance_score=float(meta.get("relevance_score", hit.get("score", 0.9)))
        )
        
        return SearchResult(
            index=index,
            title=title,
            url=meta.get("url", ""),
            source_domain=meta.get("source_domain", ""),
            data=vlm_data,
            success=True,
            from_cache=True,
            timestamp=datetime.now().isoformat()
        )

    async def _fetch_from_web(
        self,
        query: str,
        need_count: int,
        cached_results: List[SearchResult]
    ) -> List[SearchResult]:
        """从网络获取新结果"""
        browser = await self.browser_pool.acquire()
        new_results = []
        
        try:
            # 获取搜索链接
            search_links = await self._fetch_search_results(query, need_count)
            
            # 排除已缓存的 URL
            cached_urls = {r.url.lower() for r in cached_results}
            search_links = [link for link in search_links if link['url'].lower() not in cached_urls]
            
            # 按 URL 质量排序
            search_links.sort(
                key=lambda x: self.url_scorer.score(x['url'], x['title']),
                reverse=True
            )
            
            if search_links:
                logger.info(f"需要分析 {len(search_links)} 个新页面")
            
            # 批量处理页面
            for i in range(0, len(search_links), self.max_concurrent_pages):
                batch = search_links[i:i + self.max_concurrent_pages]
                
                if i > 0:
                    await asyncio.sleep(random.uniform(1.5, 3.0))
                
                tasks = [
                    self._process_single_page(browser, query, link["title"], link["url"], idx + i + 1)
                    for idx, link in enumerate(batch)
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for idx, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.error(f"[处理失败] {batch[idx]['title'][:30]}: {result}")
                        new_results.append(SearchResult(
                            index=i + idx + 1,
                            title=batch[idx]['title'],
                            url=batch[idx]['url'],
                            success=False,
                            error_message=str(result),
                            from_cache=False
                        ))
                    else:
                        new_results.append(result)
        finally:
            await self.browser_pool.release(browser)
        
        return new_results

    async def _process_single_page(
        self,
        browser,
        query: str,
        title: str,
        url: str,
        index: int
    ) -> SearchResult:
        """处理单个页面"""
        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = "unknown"
        
        logger.info(f"[{index}] 处理: {title[:50]}...")
        
        # 获取页面
        page, extracted_text, screenshot_bytes = await self.page_fetcher.fetch_page(browser, url)
        
        if page is None:
            return SearchResult(
                index=index, title=title, url=url, source_domain=domain,
                timestamp=datetime.now().isoformat(),
                success=False, error_message="页面获取失败", from_cache=False
            )
        
        try:
            # 预检测页面质量
            is_valid, reason = self.page_fetcher.validate_page_content(extracted_text)
            if not is_valid:
                logger.warning(f"[{index}] 跳过低质量页面: {reason}")
                return SearchResult(
                    index=index, title=title, url=url, source_domain=domain,
                    timestamp=datetime.now().isoformat(),
                    success=False, error_message=f"内容质量不足: {reason}", from_cache=False
                )
            
            if not screenshot_bytes:
                return SearchResult(
                    index=index, title=title, url=url, source_domain=domain,
                    timestamp=datetime.now().isoformat(),
                    success=False, error_message="截图失败", from_cache=False
                )

            # Rerank 过滤 (Strict > 0.9)
            try:
                # 拼接标题和摘要进行重排序打分
                text_content = extracted_text.get("main_text", "")[:2000]
                text_to_rank = f"{title}\n{text_content}"
                
                loop = asyncio.get_running_loop()
                rerank_result = await loop.run_in_executor(
                    None, 
                    self.rerank_client.rerank,
                    query, 
                    [text_to_rank], 
                    1
                )
                
                if rerank_result and "results" in rerank_result:
                    score = rerank_result["results"][0]["relevance_score"]
                    if score < 0.90:
                        logger.info(f"[{index}] Rerank 过滤: 评分 {score:.4f} < 0.90，跳过")
                        return SearchResult(
                            index=index, title=title, url=url, source_domain=domain,
                            timestamp=datetime.now().isoformat(),
                            success=False, 
                            error_message=f"相关性评分不足 ({score:.2f} < 0.90)", 
                            from_cache=False
                        )
                    logger.info(f"[{index}] Rerank 通过: {score:.4f}")
            except Exception as e:
                logger.warning(f"[{index}] Rerank 检查失败: {e}，默认放行")

            # 分析内容
            analysis_data = await self.content_analyzer.analyze(
                screenshot_bytes, query, title, url, extracted_text
            )

            return SearchResult(
                index=index, title=title, url=url, source_domain=domain,
                timestamp=datetime.now().isoformat(),
                data=analysis_data,
                success=analysis_data is not None,
                from_cache=False
            )
        finally:
            await self.page_fetcher.close_page(page)

    async def _fetch_search_results(self, query: str, max_results: int) -> List[dict]:
        """使用 SearXNG API 获取搜索结果"""
        all_links = []
        
        # 尝试获取百科结果
        if self.enable_baike:
            try:
                baike_link = await self._fetch_baike_result(query)
                if baike_link:
                    all_links.append(baike_link)
                    logger.info(f"找到百科结果: {baike_link['title'][:30]}...")
            except Exception as e:
                logger.warning(f"百科搜索异常: {e}")
        
        baike_link = all_links[0] if all_links else None
        
        # SearXNG 搜索
        try:
            search_url = f"{self.searxng_url}/search"
            params = self._get_searxng_params(query)
            
            response = await self.http_client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            logger.info(f"SearXNG 返回 {len(results)} 个结果")
            
            for item in results:
                url = item.get("url", "")
                title = item.get("title", "")
                
                if not url or not title:
                    continue
                if self.url_scorer.is_blacklisted(url):
                    continue
                if baike_link and url == baike_link["url"]:
                    continue
                
                all_links.append({"title": title, "url": url})
            
            return all_links[:max_results]

        except Exception as e:
            logger.error(f"SearXNG 搜索失败: {e}")
            return all_links[:max_results] if all_links else []
    
    async def _fetch_baike_result(self, query: str) -> Optional[dict]:
        """搜索百度百科结果"""
        try:
            search_url = f"{self.searxng_url}/search"
            params = self._get_searxng_params(f"{query} 百度百科")
            
            response = await self.http_client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            for item in data.get("results", []):
                url = item.get("url", "")
                title = item.get("title", "")
                
                if "baike.baidu.com/item/" in url:
                    return {
                        "title": f"【百科】{title.replace('百度百科', '').replace('_', '').strip()}",
                        "url": url
                    }
            return None
        except Exception as e:
            logger.warning(f"百科搜索失败: {e}")
            return None

    def _get_searxng_params(self, query: str) -> dict:
        """获取 SearXNG 搜索参数"""
        return {
            "q": query,
            "engines": self.searxng_engines,
            "format": "json",
            "language": self.searxng_language,
            "safesearch": 0
        }

    async def _save_to_caches(self, query: str, results: List[SearchResult]):
        """后台保存搜索结果到缓存"""
        cacheable_results = [
            r for r in results 
            if r.success and r.data and r.data.cacheable
        ]
        
        if not cacheable_results:
            logger.debug("无可缓存结果（所有结果为时效性内容）")
            return
        
        skipped_count = len(results) - len(cacheable_results)
        if skipped_count > 0:
            logger.info(f"跳过 {skipped_count} 个时效性内容，保存 {len(cacheable_results)} 个结果到缓存")
        
        try:
            if self.cache_manager.is_available:
                self.cache_manager.save_results(query, cacheable_results)
        except Exception as e:
            logger.debug(f"数据库缓存保存失败: {e}")
        
        try:
            if self.vector_cache_manager and self.vector_cache_manager.is_available:
                self.vector_cache_manager.save_results(cacheable_results)
        except Exception as e:
            logger.debug(f"向量缓存保存失败: {e}")
