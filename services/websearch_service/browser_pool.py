import asyncio
import logging
from playwright.async_api import async_playwright, Browser

logger = logging.getLogger(__name__)

class BrowserPool:
    """浏览器实例池，减少冷启动开销"""
    
    def __init__(self, pool_size: int = 3):
        """pool_size: 浏览器实例数量（建议 2-4）"""
        self.pool_size = pool_size
        self._pool: asyncio.Queue[Browser] = asyncio.Queue(pool_size)
        self._playwright = None
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        """启动时初始化浏览器池"""
        async with self._lock:
            if self._initialized:
                return
            
            self._playwright = await async_playwright().start()
            # 并行初始化所有浏览器实例
            tasks = [self._launch_browser() for _ in range(self.pool_size)]
            browsers = await asyncio.gather(*tasks)
            for browser in browsers:
                await self._pool.put(browser)
            
            self._initialized = True
            logger.info(f"浏览器池初始化完成，大小: {self.pool_size}")
    
    async def _launch_browser(self) -> Browser:
        """启动单个浏览器实例（优化参数）"""
        return await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                # 性能优化参数
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-translate",
                "--mute-audio",
                "--no-first-run",
                "--disable-default-apps",
            ]
        )
    
    async def acquire(self) -> Browser:
        """获取一个浏览器实例"""
        if not self._initialized:
            await self.initialize()
        
        browser = await self._pool.get()
        if not browser.is_connected():
            logger.warning("浏览器已断开，重新创建")
            browser = await self._launch_browser()
        return browser
    
    async def release(self, browser: Browser):
        """归还浏览器实例"""
        if browser.is_connected():
            await self._pool.put(browser)
        else:
            logger.warning("归还时浏览器已断开，创建新实例")
            new_browser = await self._launch_browser()
            await self._pool.put(new_browser)
    
    async def shutdown(self):
        """关闭所有浏览器"""
        if not self._initialized:
            return
        
        while not self._pool.empty():
            try:
                browser = await asyncio.wait_for(self._pool.get(), timeout=1.0)
                await browser.close()
            except asyncio.TimeoutError:
                break
            except Exception as e:
                logger.warning(f"关闭浏览器时出错: {e}")
        
        if self._playwright:
            await self._playwright.stop()
        
        self._initialized = False
        logger.info("浏览器池已关闭")
