"""
Agent Application Server
FastAPI application entry point
"""
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import settings
from .api.routes import router

# 配置日志
logging.basicConfig(
    level=logging.DEBUG if settings.AGENT_SERVICE_DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    """
    # 启动时
    logger.info("Starting Agent Service...")
    logger.info(f"Agent LLM Model: {settings.AGENT_LLM_MODEL_NAME}")
    logger.info(f"Max Iterations: {settings.AGENT_MAX_ITERATIONS}")
    
    # 初始化数据库（创建 Agent 相关的表）
    try:
        from storage.pgsql.database import init_db
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize database: {e}")
    
    # 初始化 Skill 执行器
    try:
        from .core.skill_executor import skill_executor
        tools = skill_executor.get_available_tools()
        logger.info(f"Loaded {len(tools)} skills: {[t['name'] for t in tools]}")
    except Exception as e:
        logger.warning(f"Failed to load skills: {e}")
    
    logger.info(f"Agent Service started on {settings.AGENT_SERVICE_HOST}:{settings.AGENT_SERVICE_PORT}")
    
    yield
    
    # 关闭时
    logger.info("Shutting down Agent Service...")
    
    # 清理资源
    try:
        from .core.skill_executor import skill_executor
        skill_executor.close()
    except Exception as e:
        logger.warning(f"Failed to close skill executor: {e}")


# 创建 FastAPI 应用
app = FastAPI(
    title="Agent Service API",
    description="""
    ## 智能 Agent 服务 API
    
    提供基于 ReAct 框架的智能 Agent 能力：
    - **自主决策**：LLM 动态选择工具链
    - **持续推理**：连续调用多个工具直到任务完成
    - **实时反馈**：SSE 流式返回执行过程
    - **会话记忆**：持久化的会话历史
    
    ### 主要接口
    - `POST /api/agent/run` - 执行 Agent 任务（流式）
    - `POST /api/agent/run/sync` - 执行 Agent 任务（同步）
    - `GET /api/agent/tools` - 获取可用工具列表
    - `GET /api/agent/sessions` - 获取会话列表
    """,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": str(exc),
                "type": "internal_error"
            }
        }
    )


# 健康检查
@app.get("/health", tags=["Health"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "agent",
        "version": "0.1.0"
    }


# 根路由
@app.get("/", tags=["Root"])
async def root():
    """根路由"""
    return {
        "message": "Welcome to Agent Service API",
        "docs": "/docs",
        "health": "/health"
    }


# 注册 API 路由
app.include_router(router, prefix="/api")


def main():
    """主函数"""
    uvicorn.run(
        "app.agent.server:app",
        host=settings.AGENT_SERVICE_HOST,
        port=settings.AGENT_SERVICE_PORT,
        reload=settings.AGENT_SERVICE_DEBUG,
        log_level="debug" if settings.AGENT_SERVICE_DEBUG else "info"
    )


if __name__ == "__main__":
    main()
