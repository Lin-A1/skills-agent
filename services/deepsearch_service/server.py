import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

# 兼容本地和 Docker 环境的导入
try:
    # 尝试从项目根目录导入（本地运行）
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from services.deepsearch_service.engine import DeepSearchEngine, DeepSearchRequest, DeepSearchResponse, DEPTH_CONFIGS
except ModuleNotFoundError:
    # Docker 环境：直接从当前目录导入
    from engine import DeepSearchEngine, DeepSearchRequest, DeepSearchResponse, DEPTH_CONFIGS

# 加载环境变量
load_dotenv()

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===== FastAPI 应用 =====
engine: Optional[DeepSearchEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global engine
    
    try:
        engine = DeepSearchEngine()
        # 启动时检查服务依赖
        await engine.check_websearch_health()
        await engine.check_rag_health()
        logger.info(f"DeepSearch 服务启动成功 - RAG: {engine._rag_enabled}")
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        raise
    
    yield
    
    if engine:
        await engine.close()
    logger.info("DeepSearch 服务已关闭")


app = FastAPI(
    title="深度搜索API",
    description="基于 LLM 的迭代式深度搜索服务，支持问题分解、多轮搜索和综合报告生成",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "DeepSearch API",
        "version": "2.0.0",
        "features": [
            "自适应搜索深度 (quick/normal/deep)",
            "LLM 驱动查询分解与优化",
            "迭代式搜索-推理循环",
            "信息去重与充分性评估",
            "带重试的下游服务调用",
            "多源综合报告生成"
        ],
        "endpoints": {
            "POST /deepsearch": "执行深度搜索",
            "GET /health": "健康检查"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查（增强版）"""
    websearch_ok = await engine.check_websearch_health() if engine else False
    
    # 报告缓存统计
    cache_size = len(engine._report_cache) if engine else 0
    
    return {
        "status": "healthy" if websearch_ok else "degraded",
        "service": "deepsearch",
        "llm_model": engine.llm_model if engine else "未初始化",
        "websearch_url": engine.websearch_url if engine else "未初始化",
        "websearch_available": websearch_ok,
        "max_iterations": engine.max_iterations if engine else 0,
        "depth_levels": list(DEPTH_CONFIGS.keys()),
        "report_cache_size": cache_size,
        "report_cache_ttl_seconds": engine.CACHE_TTL_SECONDS if engine else 0,
        "rag_enabled": engine._rag_enabled if engine else False
    }


@app.post("/deepsearch", response_model=DeepSearchResponse)
async def deepsearch(request: DeepSearchRequest):
    """
    执行深度搜索
    """
    if not engine:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    try:
        logger.info(f"收到请求: query='{request.query[:50]}...', depth={request.depth_level}")
        result = await engine.search(request)
        return result
    except Exception as e:
        logger.exception(f"深度搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("DEEPSEARCH_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("DEEPSEARCH_SERVICE_PORT", "8007"))
    
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
