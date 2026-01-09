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
    
    # 反检测脚本
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
    
    # User-Agent 列表
    USER_AGENTS = [
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]
    
    # 页面内容预检测的关键词
    PAYWALL_KEYWORDS = [
        "请登录", "需要登录", "登录后查看", "请先登录",
        "VIP专享", "付费阅读", "开通会员", "订阅后查看",
        "验证码", "请输入验证码",
    ]
    
    AD_KEYWORDS = ["广告", "立即购买", "限时优惠", "点击下载"]
    
    def __init__(
        self,
        viewport_width: int = 1440,
        viewport_height: int = 900,
        page_timeout: int = 15000,
        max_screenshot_height: int = 2500,
        device_scale_factor: int = 1,
        min_page_delay: float = 0.1,
        max_page_delay: float = 0.3
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
        context = await browser.new_context(
            user_agent=random.choice(self.USER_AGENTS),
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
            await page.goto(url, wait_until="domcontentloaded", timeout=self.page_timeout)
            await asyncio.sleep(random.uniform(0.1, 0.4))
            
            try:
                await page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass
            
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
    
    async def close_page(self, page: Page):
        """关闭页面及其上下文"""
        try:
            context = page.context
            await page.close()
            await context.close()
            await asyncio.sleep(random.uniform(self.min_page_delay, self.max_page_delay))
        except Exception as e:
            logger.warning(f"关闭页面时出错: {e}")
    
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
    
    def validate_page_content(self, extracted_text: dict) -> Tuple[bool, str]:
        """
        预检测页面内容质量
        
        Returns:
            (是否有效, 原因)
        """
        if not extracted_text:
            return False, "无法提取页面内容"
        
        main_text = extracted_text.get("main_text", "")
        
        if len(main_text) < 100:
            return False, f"内容过短({len(main_text)}字符)"
        
        # 检测付费墙/登录墙
        for kw in self.PAYWALL_KEYWORDS:
            if kw in main_text:
                return False, f"疑似付费墙/登录墙({kw})"
        
        # 检测广告页
        ad_count = sum(1 for kw in self.AD_KEYWORDS if kw in main_text)
        if ad_count >= 3:
            return False, "疑似广告页"
        
        return True, "通过"
