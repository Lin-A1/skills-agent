import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from services.websearch_service.models import SearchRequest, SearchResponse, ChatRequest
from services.websearch_service.browser_pool import BrowserPool
from services.websearch_service.storage_clients import SearchCacheManager, VectorCacheManager
from services.websearch_service.analyzer import IntelligentSearchAnalyzer

# 加载环境变量
load_dotenv()

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== 全局实例 =====
browser_pool: Optional[BrowserPool] = None
cache_manager: Optional[SearchCacheManager] = None
vector_cache_manager: Optional[VectorCacheManager] = None
analyzer: Optional[IntelligentSearchAnalyzer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global browser_pool, cache_manager, vector_cache_manager, analyzer
    
    try:
        # 初始化缓存管理器
        cache_manager = SearchCacheManager()
        cache_manager.initialize()
        
        # 初始化向量缓存管理器
        vector_cache_manager = VectorCacheManager()
        vector_cache_manager.initialize()
        
        # 初始化浏览器池（提高并发能力）
        browser_pool = BrowserPool(pool_size=5)  # 扩展池大小以支持更高并发
        await browser_pool.initialize()
        
        # 初始化搜索分析器
        analyzer = IntelligentSearchAnalyzer(browser_pool, cache_manager, vector_cache_manager)
        logger.info("FastAPI 服务启动成功")
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        raise
    
    yield
    
    # 清理资源
    if analyzer and analyzer.http_client:
        await analyzer.http_client.aclose()
    if browser_pool:
        await browser_pool.shutdown()
    logger.info("FastAPI 服务已关闭")


app = FastAPI(
    title="联网搜索API",
    description="基于 SearXNG 搜索和 OCR+LLM 的智能网页分析服务（带服务端缓存）",
    version="2.2.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "联网搜索分析 API",
        "version": "2.2.0",
        "features": [
            "浏览器池化",
            "OCR + LLM 分析",
            "双模态内容提取",
            "服务端数据库缓存",
            "结果验证重试"
        ],
        "endpoints": {
            "search": "/search",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "llm_model": analyzer.llm_model if analyzer else "未初始化",
        "browser_pool_size": browser_pool.pool_size if browser_pool else 0,
        "browser_pool_initialized": browser_pool._initialized if browser_pool else False,
        "cache_available": cache_manager.is_available if cache_manager else False,
        "vector_cache_available": vector_cache_manager.is_available if vector_cache_manager else False
    }


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    执行联网搜索分析（支持服务端缓存）
    """
    if not analyzer:
        raise HTTPException(status_code=503, detail="服务未初始化")

    try:
        logger.info(f"收到搜索请求: query='{request.query}', max_results={request.max_results}, force_refresh={request.force_refresh}")

        results, cached_count = await analyzer.search(
            request.query,
            request.max_results,
            request.force_refresh
        )

        success_count = sum(1 for r in results if r.success)

        from datetime import datetime
        return SearchResponse(
            query=request.query,
            total=len(results),
            success_count=success_count,
            cached_count=cached_count,
            results=results,
            search_timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.exception(f"搜索处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    聊天接口（流式返回）
    """
    if not analyzer:
        raise HTTPException(status_code=503, detail="服务未初始化")

    async def generate():
        try:
            # 使用 analyzer 中的 llm_client (AsyncOpenAI 实例)
            client = analyzer.llm_client
            
            stream = await client.chat.completions.create(
                model=request.model,
                messages=request.messages,
                stream=True,
                temperature=0.7
            )

            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as e:
            logger.error(f"Chat error: {e}")
            yield f"Error: {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("SEARCH_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("SEARCH_SERVICE_PORT", "8004"))

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
