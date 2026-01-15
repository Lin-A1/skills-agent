"""
页面获取模块

职责：
- 浏览器上下文管理
- 反检测脚本注入
- 页面截图捕获
- 页面文本提取
- 页面内容预检测

从 analyzer.py 提取，遵循单一职责原则。
"""
import asyncio
import logging
import random
from typing import Optional, Tuple

from playwright.async_api import Page, Browser

logger = logging.getLogger(__name__)


class PageFetcher:
    """网页内容获取器"""
    
    # 增强版反检测脚本
    ANTI_DETECTION_SCRIPT = """
    // 1. Overwrite navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    
    // 2. Mock chrome object
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {},
        webview: {},
    };
    
    // 3. Mock plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            var plugins = [];
            plugins.item = function(index) { return this[index]; };
            plugins.namedItem = function(name) { return this[name]; };
            plugins.refresh = function() {};
            
            // Add some mock plugins
            var pdfPlugin = {
                name: 'Chrome PDF Plugin',
                filename: 'internal-pdf-viewer',
                description: 'Portable Document Format'
            };
            plugins.push(pdfPlugin);
            return plugins;
        }
    });
    
    // 4. Mock languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en-US', 'en']
    });
    
    // 5. Mock permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );
    
    // 6. WebGL Vendor/Renderer Mock (Optional but recommended)
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) {
            return 'Google Inc. (NVIDIA)';
        }
        if (parameter === 37446) {
            return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
        }
        return getParameter(this, parameter);
    };
    """
    
    # 扩展的 User-Agent 列表
    USER_AGENTS = [
        # Chrome / Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        # Chrome / macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Firefox / Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        # Edge / Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    ]
    
    # 页面内容预检测的关键词
    PAYWALL_KEYWORDS = [
        "请登录", "需要登录", "登录后查看", "请先登录",
        "VIP专享", "付费阅读", "开通会员", "订阅后查看",
        "验证码", "请输入验证码",
        "Access Denied", "Captcha", "Security Check"
    ]
    
    AD_KEYWORDS = ["广告", "立即购买", "限时优惠", "点击下载"]
    
    def __init__(
        self,
        viewport_width: int = 1440,
        viewport_height: int = 900,
        page_timeout: int = 20000,  # 增加超时时间以适应模拟操作
        max_screenshot_height: int = 2500,
        device_scale_factor: int = 1,
        min_page_delay: float = 0.3,  # 减少延迟加快处理
        max_page_delay: float = 0.8
    ):
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.page_timeout = page_timeout
        self.max_screenshot_height = max_screenshot_height
        self.device_scale_factor = device_scale_factor
        self.min_page_delay = min_page_delay
        self.max_page_delay = max_page_delay
    
    async def create_context(self, browser: Browser):
        """创建浏览器上下文（带反检测）"""
        user_agent = random.choice(self.USER_AGENTS)
        
        context = await browser.new_context(
            user_agent=user_agent,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            device_scale_factor=self.device_scale_factor,
            ignore_https_errors=True,
            java_script_enabled=True,
            has_touch=False,  # Desktop usually doesn't have touch
            is_mobile=False,
            color_scheme="light",
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',  # Should match User-Agent OS ideally, keeping simple for now
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }
        )
        
        # 注入初始化脚本
        await context.add_init_script(self.ANTI_DETECTION_SCRIPT)
        return context
    
    async def fetch_page(
        self, 
        browser: Browser, 
        url: str
    ) -> Tuple[Optional[Page], Optional[dict], Optional[bytes]]:
        """
        获取页面内容
        
        Returns:
            (page, extracted_text, screenshot_bytes) 元组
            失败时返回 (None, None, None)
        """
        context = await self.create_context(browser)
        page = await context.new_page()
        
        try:
            # 随机化视口大小，避免完全一致的指纹
            width = self.viewport_width + random.randint(-50, 50)
            height = self.viewport_height + random.randint(-50, 50)
            await page.set_viewport_size({"width": width, "height": height})

            response = await page.goto(url, wait_until="domcontentloaded", timeout=self.page_timeout)
            
            # 检查响应状态
            if response and response.status >= 400:
                logger.warning(f"页面返回错误状态码: {response.status} - {url}")
                if response.status in [403, 429]: # Forbidden or Too Many Requests
                     logger.warning("疑似被反爬拦截")
            
            # 等待网络闲置，但不要太久
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            
            # 模拟人类行为 (随机鼠标移动、滚动)
            await self._simulate_human_behavior(page)
            
            # 再次等待少量时间，确保动态内容加载
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # 并行提取文本和截图
            screenshot_task = self._capture_screenshot(page)
            text_task = self._extract_page_content(page)
            
            screenshot_bytes, extracted_text = await asyncio.gather(
                screenshot_task, text_task, return_exceptions=True
            )
            
            if isinstance(screenshot_bytes, Exception):
                screenshot_bytes = None
            if isinstance(extracted_text, Exception):
                extracted_text = {}
            
            return page, extracted_text, screenshot_bytes
            
        except Exception as e:
            logger.error(f"页面获取失败: {url} - {e}")
            await page.close()
            await context.close()
            return None, None, None
    
    async def _simulate_human_behavior(self, page: Page):
        """模拟人类操作行为：快速版（减少等待时间）"""
        try:
            # 1. 简化鼠标移动（1-2 次）
            for _ in range(random.randint(1, 2)):
                x = random.randint(200, self.viewport_width - 200)
                y = random.randint(150, self.viewport_height - 150)
                await page.mouse.move(x, y, steps=3)  # 减少步数
                await asyncio.sleep(random.uniform(0.05, 0.15))  # 减少延迟
            
            # 2. 快速滚动到页面中部再回顶部
            total_height = await page.evaluate("document.body.scrollHeight")
            scroll_target = min(total_height // 2, 1000)  # 最多滚动 1000px
            
            # 一次性滚动
            await page.mouse.wheel(0, scroll_target)
            await asyncio.sleep(random.uniform(0.2, 0.4))
            
            # 滚回顶部以便截图
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.2)
            
        except Exception as e:
            logger.warning(f"模拟人类行为失败: {e}")

    async def close_page(self, page: Page):
        """关闭页面及其上下文"""
        try:
            if not page.is_closed():
                context = page.context
                await page.close()
                await context.close()
            # 随机延迟，避免频繁请求
            await asyncio.sleep(random.uniform(self.min_page_delay, self.max_page_delay))
        except Exception as e:
            logger.warning(f"关闭页面时出错: {e}")
    
    async def _capture_screenshot(self, page: Page) -> Optional[bytes]:
        """捕获页面截图"""
        try:
            # 确保在截图前回到顶部 (在 simulate里面已经做了，这里再保险一次)
            # await page.evaluate("window.scrollTo(0, 0)")
            
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
                        // 移除干扰元素
                        const toRemove = ['script', 'style', 'noscript', 'iframe', 'header', 'footer', 'nav', '.ad', '.ads', '.advertisement'];
                        toRemove.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));

                        const selectors = ['article', 'main', '.content', '#content', '.article', '.post', '.news-detail'];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el && el.innerText.length > 200) {
                                return el.innerText.slice(0, 4000).trim();
                            }
                        }
                        return document.body?.innerText?.slice(0, 4000).trim() || '';
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
    
    def validate_page_content(self, extracted_text: dict) -> Tuple[bool, str]:
        """
        预检测页面内容质量
        
        Returns:
            (是否有效, 原因)
        """
        if not extracted_text:
            return False, "无法提取页面内容"
        
        main_text = extracted_text.get("main_text", "")
        
        if len(main_text) < 50: # 稍微放宽长度限制
            return False, f"内容过短({len(main_text)}字符)"
        
        # 检测付费墙/登录墙
        for kw in self.PAYWALL_KEYWORDS:
            if kw in main_text:
                # 再次确认是否真的是阻断性提示，有些文章只是提到
                if len(main_text) < 500: 
                    return False, f"疑似付费墙/登录墙({kw})"
        
        # 检测广告页
        ad_count = sum(1 for kw in self.AD_KEYWORDS if kw in main_text)
        if ad_count >= 3 and len(main_text) < 800:
            return False, "疑似广告页"
        
        return True, "通过"
