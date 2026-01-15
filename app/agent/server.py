"""
Agent Application Server
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
from .database import init_db
from .api import router
from .core import get_skill_registry

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
    logger.info(f"Database: {settings.PGSQL_HOST}:{settings.PGSQL_PORT}/{settings.PGSQL_DATABASE}")
    logger.info(f"Agent LLM Model: {settings.AGENT_LLM_MODEL_NAME}")
    logger.info(f"Skills Directory: {settings.SKILLS_DIRECTORY}")
    
    # 初始化数据库
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # 发现并注册 Skills
    try:
        registry = get_skill_registry()
        skills = registry.list_skills()
        logger.info(f"Discovered {len(skills)} skills:")
        for skill in skills:
            logger.info(f"  - {skill.name}: {skill.description[:50]}...")
    except Exception as e:
        logger.warning(f"Failed to discover skills: {e}")
    
    # 显示当前日期信息
    date_info = settings.get_current_date_info()
    logger.info(f"Current date: {date_info['date']} ({date_info['weekday']})")
    
    logger.info(f"Agent Service started on {settings.AGENT_SERVICE_HOST}:{settings.AGENT_SERVICE_PORT}")
    
    yield
    
    # 关闭时
    logger.info("Shutting down Agent Service...")


# 创建 FastAPI 应用
app = FastAPI(
    title="Agent Service API",
    description="""
    ## Agent 服务 API
    
    基于 Agent Skills 模式的智能代理服务，支持：
    - 会话管理（创建、更新、删除、列表）
    - 消息历史存储
    - 持久化记忆
    - Skills 发现与执行
    - 流式和非流式响应
    
    ### 核心特性
    - **Skills 集成**: 自动发现 SKILL.md 文件，通过 Sandbox 安全执行
    - **多轮调用**: 支持一次回答中多次调用 Skills
    - **记忆持久化**: 会话级和全局级记忆管理
    - **流式输出**: 实时返回思考过程和执行结果
    
    ### API 设计
    API 设计参考 OpenAI 格式，方便与现有工具集成。
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
    from .core import get_skill_executor
    
    # 检查 Sandbox 服务
    executor = get_skill_executor()
    sandbox_health = executor.health_check()
    
    return {
        "status": "healthy",
        "service": "agent",
        "version": "0.1.0",
        "sandbox": sandbox_health,
        "date": settings.get_current_date_info()["date"]
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
