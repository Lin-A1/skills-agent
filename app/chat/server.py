"""
Chat Application Server
FastAPI application entry point
"""
import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import settings
from .database import init_db  # 使用共享的数据库初始化
from .api import router

# 配置日志
logging.basicConfig(
    level=logging.DEBUG if settings.CHAT_SERVICE_DEBUG else logging.INFO,
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
    logger.info("Starting Chat Service...")
    logger.info(f"Database: {settings.PGSQL_HOST}:{settings.PGSQL_PORT}/{settings.PGSQL_DATABASE}")
    logger.info(f"Chat LLM Model: {settings.CHAT_LLM_MODEL_NAME}")
    
    # 初始化数据库
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    logger.info(f"Chat Service started on {settings.CHAT_SERVICE_HOST}:{settings.CHAT_SERVICE_PORT}")
    
    yield
    
    # 关闭时
    logger.info("Shutting down Chat Service...")


# 创建FastAPI应用
app = FastAPI(
    title="Chat Service API",
    description="""
    ## 聊天服务API
    
    提供类似OpenAI的聊天完成接口，支持：
    - 会话管理（创建、更新、删除、列表）
    - 消息历史存储
    - 上下文管理
    - 流式和非流式响应
    
    ### 兼容性
    API设计兼容OpenAI Chat Completion格式，可以方便地与现有工具集成。
    """,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# 配置CORS
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
        "service": "chat",
        "version": "0.1.0"
    }


# 根路由
@app.get("/", tags=["Root"])
async def root():
    """根路由"""
    return {
        "message": "Welcome to Chat Service API",
        "docs": "/docs",
        "health": "/health"
    }


# 注册API路由
app.include_router(router, prefix="/api")


def main():
    """主函数"""
    uvicorn.run(
        "app.chat.server:app",
        host=settings.CHAT_SERVICE_HOST,
        port=settings.CHAT_SERVICE_PORT,
        reload=settings.CHAT_SERVICE_DEBUG,
        log_level="debug" if settings.CHAT_SERVICE_DEBUG else "info"
    )


if __name__ == "__main__":
    main()
