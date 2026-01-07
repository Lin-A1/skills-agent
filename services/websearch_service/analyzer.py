import asyncio
import base64
import json
import logging
import os
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI
from playwright.async_api import Page, Browser

from .models import VLMAnalysisData, SearchResult
from .browser_pool import BrowserPool
from .storage_clients import SearchCacheManager, VectorCacheManager

# OCR 客户端
try:
    from services.ocr_service.client import OCRServiceClient
except ImportError:
    # 容器内路径
    import sys
    sys.path.insert(0, '/app')
    from services.ocr_service.client import OCRServiceClient

logger = logging.getLogger(__name__)

class IntelligentSearchAnalyzer:
    """联网搜索分析器"""
    
    # 黑名单域名（低质量内容源）- 使用 frozenset 加速查找
    BLACKLIST_DOMAINS = frozenset([
        "zhihu.com", "zhuanlan.zhihu.com", "csdn.net", "blog.csdn.net",
        "360doc.com", "docin.com", "doc88.com", "wenku.baidu.com",
        "jianshu.com", "bokeyuan.cn",
        "sohu.com", "163.com", "sina.com.cn",
        "toutiao.com", "ixigua.com", "toutiaocdn.com",
        "bilibili.com", "youku.com", "iqiyi.com",
        "weibo.com", "weixin.qq.com", "mp.weixin.qq.com",
        "tieba.baidu.com",
        "zhidao.baidu.com", "wenwen.sogou.com", "wenda.so.com",
    ])
    
    # 黑名单域名后缀（用于快速匹配 bbs.xxx.com, forum.xxx.com 等）
    BLACKLIST_DOMAIN_PREFIXES = frozenset(["bbs.", "forum."])
    
    # 权威来源域名（高质量加分）
    AUTHORITATIVE_DOMAINS = frozenset([
        "gov.cn", ".edu.cn", ".edu", ".ac.cn",
        "wikipedia.org", "baike.baidu.com", "baike.sogou.com",
        "developer.mozilla.org", "docs.python.org", "docs.microsoft.com",
        "developer.apple.com", "cloud.google.com/docs",
        "github.com", "gitlab.com", "gitee.com",
        "arxiv.org", "scholar.google.com", "cnki.net",
        "engineering.fb.com", "ai.google", "openai.com/blog",
    ])
    
    # URL 路径黑名单（登录/广告/无效页）
    BLACKLIST_URL_PATTERNS = frozenset([
        "/login", "/signin", "/register", "/signup",
        "/ad/", "/ads/", "/advert", "/banner",
        "/cart", "/checkout", "/payment",
        "/404", "/error", "/not-found",
        "?ref=", "?utm_", "?from=",
    ])

    ANTI_DETECTION_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { 
        get: () => [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
            {name: 'Native Client', filename: 'internal-nacl-plugin'}
        ]
    });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
    window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 1 });
    Object.defineProperty(navigator, 'platform', { get: () => 'Linux x86_64' });
    """

    # OCR + LLM 分析提示词模板（纯文本，不需要图片）
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


    LLM_MAX_TOKENS = 2000
    LLM_TEMPERATURE = 0.3
    LLM_TIMEOUT = 60.0

    def __init__(self, browser_pool: BrowserPool, cache_manager: SearchCacheManager, vector_cache_manager: VectorCacheManager = None):
        # LLM 配置 (使用普通 LLM，不需要视觉能力)
        self.llm_model = os.getenv("LLM_MODEL_NAME", "qwen-plus")
        self.llm_url = os.getenv("LLM_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        
        self.searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8005")
        self.searxng_timeout = float(os.getenv("SEARXNG_TIMEOUT", "10.0"))
        self.searxng_engines = os.getenv("SEARXNG_ENGINES", "bing,baidu,360search")
        self.searxng_language = os.getenv("SEARXNG_LANGUAGE", "zh-CN")

        if not self.llm_api_key:
            raise ValueError("LLM_API_KEY 未配置，请检查环境变量")

        # LLM 客户端
        self.llm_client = AsyncOpenAI(api_key=self.llm_api_key, base_url=self.llm_url)
        self.llm_semaphore = asyncio.Semaphore(5)
        
        # OCR 客户端
        ocr_host = os.getenv("OCR_HOST", "ocr_service")
        ocr_port = os.getenv("OCR_PORT", "8001")
        self.ocr_client = OCRServiceClient(base_url=f"http://{ocr_host}:{ocr_port}")
        self.ocr_executor = ThreadPoolExecutor(max_workers=5)  # 用于异步调用同步 OCR
        
        self.http_client = httpx.AsyncClient(
            timeout=self.searxng_timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )
        
        self.browser_pool = browser_pool
        self.cache_manager = cache_manager
        self.vector_cache_manager = vector_cache_manager

        # 页面配置
        self.viewport_width = 1440
        self.viewport_height = 900
        self.page_timeout = 20000
        self.max_screenshot_height = 3000
        self.device_scale_factor = 1
        self.max_concurrent_pages = 5
        self.min_page_delay = 0.2
        self.max_page_delay = 0.5
        
        # 质量阈值
        self.min_content_length = 150
        self.min_key_info_count = 2
        self.min_relevance_score = 0.3
        self.max_retry_count = 1
        
        # 结果过滤配置
        self.max_same_domain_results = 2
        
        self.enable_baike = os.getenv("ENABLE_BAIKE_SEARCH", "true").lower() == "true"

        logger.info(f"初始化完成 - LLM模型: {self.llm_model}, OCR: {ocr_host}:{ocr_port}, 并发: {self.max_concurrent_pages}页面/{self.llm_semaphore._value}LLM")

    def _score_url_quality(self, url: str, title: str) -> float:
        """快速评估 URL 质量（0.0-1.0）"""
        score = 0.5
        url_lower = url.lower()
        title_lower = (title or "").lower()
        
        # 1. 权威来源加分
        for domain in self.AUTHORITATIVE_DOMAINS:
            if domain in url_lower:
                score += 0.35
                break
        
        # 2. 百科类特殊加分
        if "baike." in url_lower or "wikipedia." in url_lower:
            score += 0.25
        
        # 3. URL 路径质量检测
        for pattern in self.BLACKLIST_URL_PATTERNS:
            if pattern in url_lower:
                score -= 0.3
                break
        
        # 4. 标题质量评估
        if title:
            if 10 < len(title) < 80:
                score += 0.1
            spam_keywords = ["震惊", "必看", "速看", "转发", "点击", "免费", "限时"]
            if any(kw in title_lower for kw in spam_keywords):
                score -= 0.2
        
        # 5. URL 特征加分
        if "/docs/" in url_lower or "/documentation/" in url_lower:
            score += 0.15
        if "/api/" in url_lower and ("reference" in url_lower or "doc" in url_lower):
            score += 0.1
        
        return min(1.0, max(0.0, score))

    async def search(self, query: str, max_results: int = 5, force_refresh: bool = False) -> tuple[List[SearchResult], int]:
        """执行搜索并分析（支持缓存）"""
        search_start_time = datetime.now()
        logger.info(f"开始搜索: '{query}' (最多 {max_results} 个结果, 强制刷新: {force_refresh})")
        
        cached_results = []
        cached_count = 0
        
        # 1. 检查缓存
        if not force_refresh:
            # 1.1 尝试向量语义搜索 (相似度 > 0.95)
            if self.vector_cache_manager and self.vector_cache_manager.is_available:
                try:
                    logger.info(f"执行向量语义搜索: {query}")
                    vector_hits = self.vector_cache_manager.semantic_search(
                        query, 
                        top_k=max_results, 
                        min_score=0.85,
                        rerank=True
                    )
                    
                    if vector_hits:
                        logger.info(f"向量缓存命中: 找到 {len(vector_hits)} 个高相似度结果")
                        for i, hit in enumerate(vector_hits):
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
                            
                            cached_results.append(SearchResult(
                                index=i + 1,
                                title=title,
                                url=meta.get("url", ""),
                                source_domain=meta.get("source_domain", ""),
                                data=vlm_data,
                                success=True,
                                from_cache=True,
                                timestamp=datetime.now().isoformat()
                            ))
                except Exception as e:
                    logger.warning(f"向量缓存查询失败: {e}")

            # 1.2 如果向量结果不足，尝试普通数据库缓存补充
            if len(cached_results) < max_results and self.cache_manager.is_available:
                keyword_results = self.cache_manager.search_cache(query, max_results)
                
                existing_urls = {r.url for r in cached_results}
                for res in keyword_results:
                    if res.url not in existing_urls:
                        cached_results.append(res)
                        existing_urls.add(res.url)
                
            cached_results = cached_results[:max_results]
            cached_count = len(cached_results)
            
            if cached_count >= max_results:
                logger.info(f"缓存完全命中: {cached_count} 条结果")
                return cached_results, cached_count
            
            logger.info(f"缓存部分命中: {cached_count} 条，需补充 {max_results - cached_count} 条")
        
        # 2. 需要补充的数量
        need_count = max_results - cached_count
        new_results = []
        
        # 3. 从网络获取新结果
        browser = await self.browser_pool.acquire()
        
        try:
            search_links = await self._fetch_search_results(query, need_count)
            
            cached_urls = {r.url.lower() for r in cached_results}
            search_links = [link for link in search_links if link['url'].lower() not in cached_urls]
            
            search_links.sort(
                key=lambda x: self._score_url_quality(x['url'], x['title']),
                reverse=True
            )
            
            if search_links:
                logger.info(f"需要分析 {len(search_links)} 个新页面")
            
            for i in range(0, len(search_links), self.max_concurrent_pages):
                batch = search_links[i:i + self.max_concurrent_pages]
                
                if i > 0:
                    await asyncio.sleep(random.uniform(0.3, 0.6))
                
                tasks = [
                    self._process_single_page(browser, query, link["title"], link["url"], idx + i + 1)
                    for idx, link in enumerate(batch)
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for idx, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.error(f"[处理失败] {batch[idx]['title'][:30]}: {result}")
                        new_results.append(SearchResult(
                            index=cached_count + i + idx + 1,
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
        
        # 4. 后台保存缓存（不阻塞响应返回）
        if new_results:
            asyncio.create_task(self._save_to_caches(query, new_results))
        
        # 5. 合并和过滤结果
        all_results = cached_results + new_results
        
        filtered_results = []
        for r in all_results:
            if r.success and r.data and r.data.relevance_score >= self.min_relevance_score:
                filtered_results.append(r)
            elif r.from_cache:
                filtered_results.append(r)
        
        def sort_key(r):
            if r.data:
                return (1 if r.success else 0, r.data.relevance_score)
            return (0, 0)
        filtered_results.sort(key=sort_key, reverse=True)
        
        domain_count = {}
        deduped_results = []
        for r in filtered_results:
            domain = r.source_domain or "unknown"
            count = domain_count.get(domain, 0)
            if count < self.max_same_domain_results:
                deduped_results.append(r)
                domain_count[domain] = count + 1
        
        final_results = deduped_results[:max_results]
        
        for idx, result in enumerate(final_results, 1):
            result.index = idx
        
        success_count = sum(1 for r in final_results if r.success)
        elapsed = (datetime.now() - search_start_time).total_seconds()
        logger.info(f"搜索完成: 成功 {success_count}/{len(final_results)} 个, 缓存 {cached_count} 个, 耗时 {elapsed:.2f}s")
        
        return final_results, cached_count

    async def _save_to_caches(self, query: str, results: List[SearchResult]):
        """后台保存搜索结果到缓存（不阻塞主流程）"""
        # 只保存 cacheable=True 的结果（过滤时效性内容）
        cacheable_results = [
            r for r in results 
            if r.success and r.data and r.data.cacheable
        ]
        
        if not cacheable_results:
            logger.debug(f"无可缓存结果（所有结果为时效性内容）")
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


    async def _create_context(self, browser: Browser):
        """创建浏览器上下文"""
        user_agents = [
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        ]
        
        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            device_scale_factor=self.device_scale_factor,
            ignore_https_errors=True,
            java_script_enabled=True,
            has_touch=True,
            is_mobile=False,
            color_scheme="light",
        )
        await context.add_init_script(self.ANTI_DETECTION_SCRIPT)
        return context

    async def _fetch_search_results(self, query: str, max_results: int) -> List[dict]:
        """使用 SearXNG API 获取搜索结果"""
        all_links = []
        
        if self.enable_baike:
            try:
                baike_link = await self._fetch_baike_result(query)
                if baike_link:
                    all_links.append(baike_link)
                    logger.info(f"找到百科结果: {baike_link['title'][:30]}...")
            except Exception as e:
                logger.warning(f"百科搜索异常: {e}")
        
        baike_link = all_links[0] if all_links else None
        
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
                if self._is_blacklisted(url):
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

    async def _process_single_page(self, browser: Browser, query: str,
                                   title: str, url: str, index: int) -> SearchResult:
        """处理单个页面（带内容预检测）"""
        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = "unknown"
        
        context = await self._create_context(browser)
        page = await context.new_page()

        try:
            logger.info(f"[{index}] 处理: {title[:50]}...")

            await page.goto(url, wait_until="domcontentloaded", timeout=self.page_timeout)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass

            screenshot_task = self._capture_screenshot(page)
            text_task = self._extract_page_content(page)
            
            screenshot_bytes, extracted_text = await asyncio.gather(
                screenshot_task, text_task, return_exceptions=True
            )
            
            if isinstance(screenshot_bytes, Exception):
                screenshot_bytes = None
            if isinstance(extracted_text, Exception):
                extracted_text = {}
            
            is_valid, reason = self._validate_page_content(extracted_text)
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

            analysis_data = await self._analyze_with_retry(
                screenshot_bytes, query, title, url, extracted_text
            )

            return SearchResult(
                index=index, title=title, url=url, source_domain=domain,
                timestamp=datetime.now().isoformat(),
                data=analysis_data,
                success=analysis_data is not None,
                from_cache=False
            )

        except Exception as e:
            logger.error(f"[{index}] 处理失败: {e}")
            return SearchResult(
                index=index, title=title, url=url, source_domain=domain,
                timestamp=datetime.now().isoformat(),
                success=False, error_message=str(e), from_cache=False
            )
        finally:
            await page.close()
            await context.close()
            await asyncio.sleep(random.uniform(self.min_page_delay, self.max_page_delay))

    def _is_blacklisted(self, url: str) -> bool:
        """检查URL是否在黑名单中（优化版）"""
        url_lower = url.lower()
        
        # 1. 提取域名并检查黑名单
        try:
            parsed = urlparse(url_lower)
            domain = parsed.netloc
            
            # 检查域名前缀（bbs., forum.）
            for prefix in self.BLACKLIST_DOMAIN_PREFIXES:
                if domain.startswith(prefix):
                    return True
            
            # 检查域名是否在黑名单中（包含匹配）
            for blacklisted in self.BLACKLIST_DOMAINS:
                if blacklisted in domain:
                    return True
        except Exception:
            pass
        
        # 2. 检查 URL 路径黑名单
        for pattern in self.BLACKLIST_URL_PATTERNS:
            if pattern in url_lower:
                return True
        
        return False
    
    def _validate_page_content(self, extracted_text: dict) -> tuple[bool, str]:
        """预检测页面内容质量"""
        if not extracted_text:
            return False, "无法提取页面内容"
        
        main_text = extracted_text.get("main_text", "")
        
        if len(main_text) < 100:
            return False, f"内容过短({len(main_text)}字符)"
        
        paywall_keywords = [
            "请登录", "需要登录", "登录后查看", "请先登录",
            "VIP专享", "付费阅读", "开通会员", "订阅后查看",
            "验证码", "请输入验证码",
        ]
        for kw in paywall_keywords:
            if kw in main_text:
                return False, f"疑似付费墙/登录墙({kw})"
        
        ad_keywords = ["广告", "立即购买", "限时优惠", "点击下载"]
        ad_count = sum(1 for kw in ad_keywords if kw in main_text)
        if ad_count >= 3:
            return False, "疑似广告页"
        
        return True, "通过"
    
    async def _extract_page_content(self, page: Page) -> dict:
        """提取页面文本"""
        try:
            return await page.evaluate("""
                () => {
                    const getText = (selector, maxLen = 500) => {
                        const el = document.querySelector(selector);
                        return el ? el.innerText.slice(0, maxLen).trim() : '';
                    };
                    const getMainText = () => {
                        const selectors = ['article', 'main', '.content', '#content', '.article', '.post'];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el && el.innerText.length > 200) {
                                return el.innerText.slice(0, 3000).trim();
                            }
                        }
                        return document.body?.innerText?.slice(0, 3000).trim() || '';
                    };
                    return {
                        title: document.title || '',
                        h1: getText('h1', 200),
                        meta_description: document.querySelector('meta[name="description"]')?.content || '',
                        main_text: getMainText()
                    };
                }
            """)
        except Exception as e:
            logger.warning(f"提取页面文本失败: {e}")
            return {}

    async def _capture_screenshot(self, page: Page) -> Optional[bytes]:
        """捕获页面截图"""
        try:
            await page.wait_for_selector("body", timeout=self.page_timeout)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.4)
            
            page_height = await page.evaluate("document.body.scrollHeight")
            
            if page_height > self.max_screenshot_height:
                return await page.screenshot(
                    full_page=False, type="jpeg", quality=75,
                    clip={"x": 0, "y": 0, "width": self.viewport_width, "height": self.max_screenshot_height}
                )
            else:
                return await page.screenshot(full_page=True, type="jpeg", quality=75)
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    @staticmethod
    def _clean_json_response(text: str) -> str:
        """清理 VLM 返回的 JSON 文本"""
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _get_searxng_params(self, query: str) -> dict:
        """获取 SearXNG 搜索参数"""
        return {
            "q": query,
            "engines": self.searxng_engines,
            "format": "json",
            "language": self.searxng_language,
            "safesearch": 0
        }

    def _validate_result(self, data: VLMAnalysisData) -> bool:
        """验证 VLM 返回结果质量"""
        if not data:
            return False
        if len(data.main_content) < self.min_content_length:
            return False
        if len(data.key_information) < self.min_key_info_count:
            return False
        if data.relevance_score < self.min_relevance_score:
            return False
        return True

    async def _analyze_with_retry(self, image_bytes: bytes, query: str,
                                   title: str, url: str, 
                                   extracted_text: dict) -> Optional[VLMAnalysisData]:
        """带重试的 OCR + LLM 分析"""
        result = None
        for attempt in range(self.max_retry_count + 1):
            result = await self._analyze_with_ocr_llm(image_bytes, query, title, url, extracted_text)
            if result and self._validate_result(result):
                return result
            if attempt < self.max_retry_count:
                await asyncio.sleep(0.5)
        return result

    async def _ocr_image(self, image_bytes: bytes) -> str:
        """异步调用 OCR 服务提取图片文本"""
        try:
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # 使用线程池执行同步 OCR 调用
            loop = asyncio.get_event_loop()
            ocr_result = await loop.run_in_executor(
                self.ocr_executor,
                self.ocr_client.ocr,
                image_base64
            )
            
            # 提取 OCR 文本
            if isinstance(ocr_result, list):
                # OCR 返回的是文本行列表
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
                
        except Exception as e:
            logger.warning(f"OCR 提取失败: {e}")
            return ""

    async def _analyze_with_ocr_llm(self, image_bytes: bytes, query: str,
                                    title: str, url: str,
                                    extracted_text: dict) -> Optional[VLMAnalysisData]:
        """使用 OCR + LLM 分析截图（替代 VLM）"""
        try:
            # 1. OCR 提取截图中的文本
            ocr_text = await self._ocr_image(image_bytes)
            
            # 2. 构建页面文本摘要
            text_summary = ""
            if extracted_text:
                parts = []
                if extracted_text.get("title"):
                    parts.append(f"标题: {extracted_text['title']}")
                if extracted_text.get("h1"):
                    parts.append(f"主标题: {extracted_text['h1']}")
                if extracted_text.get("meta_description"):
                    parts.append(f"描述: {extracted_text['meta_description']}")
                if extracted_text.get("main_text"):
                    parts.append(f"正文摘要: {extracted_text['main_text'][:1500]}")
                text_summary = "\n".join(parts) if parts else "（未提取到文本）"
            else:
                text_summary = "（未提取到文本）"
            
            # 3. 构建 LLM 提示词（纯文本，无图片）
            ocr_text_summary = ocr_text[:2000] if ocr_text else "（OCR 未提取到文本）"
            prompt = self.LLM_ANALYSIS_PROMPT_TEMPLATE.format(
                query=query, 
                extracted_text=text_summary,
                ocr_text=ocr_text_summary
            )

            # 4. 调用 LLM（纯文本对话，不需要视觉能力）
            async with self.llm_semaphore:
                try:
                    response = await asyncio.wait_for(
                        self.llm_client.chat.completions.create(
                            model=self.llm_model,
                            messages=[{
                                "role": "user",
                                "content": prompt  # 纯文本，不含图片
                            }],
                            max_tokens=self.LLM_MAX_TOKENS,
                            temperature=self.LLM_TEMPERATURE
                        ),
                        timeout=self.LLM_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.error(f"LLM 调用超时")
                    return None

            result_text = response.choices[0].message.content.strip()
            result_text = self._clean_json_response(result_text)

            data = json.loads(result_text)
            
            required_fields = ['title_summary', 'main_content', 'key_information', 'credibility', 'relevance_score']
            if any(f not in data for f in required_fields):
                return None
            
            valid_credibility = ['authoritative', 'commercial', 'forum', 'unknown']
            if data['credibility'] not in valid_credibility:
                data['credibility'] = 'unknown'
            
            # 确保 cacheable 字段有值，默认为 True
            if 'cacheable' not in data:
                data['cacheable'] = True
            
            return VLMAnalysisData(**data)


        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"OCR+LLM 分析失败: {e}")
            return None
