"""
沙盒服务 - FastAPI 入口
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# 兼容本地和 Docker 环境的导入
try:
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from services.sandbox_service.executor import CodeExecutor, ExecutionResult, LANGUAGE_CONFIG
except ModuleNotFoundError:
    from executor import CodeExecutor, ExecutionResult, LANGUAGE_CONFIG

# 加载环境变量
load_dotenv()

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===== Pydantic 模型 =====
class ExecuteRequest(BaseModel):
    """代码执行请求"""
    code: str = Field(..., description="要执行的代码", min_length=1, max_length=50000)
    language: str = Field("python", description="编程语言 (python/shell/bash)")
    timeout: Optional[int] = Field(None, description="超时时间（秒）", ge=1, le=120)
    env_vars: Optional[Dict[str, str]] = Field(None, description="环境变量")
    trusted_mode: bool = Field(
        False, 
        description="信任模式：允许访问 services 模块和网络，可以 from services.xxx.client import ..."
    )



class ExecuteResponse(BaseModel):
    """代码执行响应"""
    success: bool = Field(..., description="执行是否成功")
    stdout: str = Field(..., description="标准输出")
    stderr: str = Field(..., description="标准错误")
    exit_code: int = Field(..., description="退出码")
    execution_time: float = Field(..., description="执行时间（秒）")
    error: Optional[str] = Field(None, description="错误信息")


# ===== FastAPI 应用 =====
executor: Optional[CodeExecutor] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global executor
    
    cleanup_task = None
    
    try:
        executor = CodeExecutor()
        
        # 检查 Docker 是否可用
        docker_ok = await executor.check_docker_available()
        if not docker_ok:
            logger.error("Docker 不可用，沙盒服务将无法正常工作")
        else:
            logger.info("Docker 检查通过")
            # 启动定期清理任务
            cleanup_task = asyncio.create_task(periodic_cleanup())
        
        logger.info("Sandbox 服务启动成功")
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        raise
    
    yield
    
    # 关闭清理任务
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    
    logger.info("Sandbox 服务已关闭")


async def periodic_cleanup():
    """定期清理孤儿容器和未使用的镜像"""
    import asyncio
    
    cleanup_interval = int(os.getenv("SANDBOX_CLEANUP_INTERVAL", "300"))  # 默认5分钟
    
    while True:
        try:
            await asyncio.sleep(cleanup_interval)
            
            # 清理已停止的沙盒容器
            logger.info("开始定期清理...")
            
            # 清理名称以 sandbox_ 开头的容器
            process = await asyncio.create_subprocess_exec(
                "docker", "container", "ls", "-aq", "--filter", "name=sandbox_",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await process.communicate()
            container_ids = stdout.decode().strip().split('\n')
            container_ids = [c for c in container_ids if c]
            
            if container_ids:
                logger.info(f"发现 {len(container_ids)} 个残留沙盒容器，正在清理...")
                for cid in container_ids:
                    try:
                        rm_process = await asyncio.create_subprocess_exec(
                            "docker", "rm", "-f", cid,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL
                        )
                        await rm_process.wait()
                    except Exception:
                        pass
                logger.info("容器清理完成")
            
            # 清理悬空镜像（可选，每小时执行一次）
            # 这里暂时不执行，避免影响其他服务
            
        except asyncio.CancelledError:
            logger.info("清理任务已取消")
            break
        except Exception as e:
            logger.warning(f"清理任务出错: {e}")


app = FastAPI(
    title="代码沙盒服务",
    description="安全的代码执行沙盒，支持 Python/Shell/Bash",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Sandbox Service",
        "version": "1.0.0",
        "description": "安全的代码执行沙盒服务",
        "supported_languages": list(LANGUAGE_CONFIG.keys()),
        "endpoints": {
            "POST /execute": "执行代码",
            "GET /health": "健康检查"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    docker_ok = await executor.check_docker_available() if executor else False
    
    return {
        "status": "healthy" if docker_ok else "degraded",
        "service": "sandbox",
        "docker_available": docker_ok,
        "timeout": executor.timeout if executor else 0,
        "memory_limit": executor.memory_limit if executor else "N/A",
        "cpu_limit": executor.cpu_limit if executor else "N/A",
        "supported_languages": [lang.value for lang in LANGUAGE_CONFIG.keys()]
    }


@app.post("/execute", response_model=ExecuteResponse)
async def execute_code(request: ExecuteRequest):
    """
    执行代码
    
    模式说明：
    - 隔离模式（默认）：禁用网络、只读文件系统、严格安全限制
    - 信任模式（trusted_mode=True）：
      - 允许访问 myagent_network 网络
      - 可以 from services.xxx.client import ... 调用其他服务
      - 适合 Agent 代码融合场景
    """
    if not executor:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    try:
        mode = "trusted" if request.trusted_mode else "isolated"
        logger.info(f"执行请求: language={request.language}, mode={mode}, code_length={len(request.code)}")
        
        result = await executor.execute(
            code=request.code,
            language=request.language,
            timeout=request.timeout,
            env_vars=request.env_vars,
            trusted_mode=request.trusted_mode
        )
        
        return ExecuteResponse(
            success=result.success,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            execution_time=result.execution_time,
            error=result.error
        )
        
    except Exception as e:
        logger.exception(f"代码执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))



if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("SANDBOX_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("SANDBOX_SERVICE_PORT", "8009"))
    
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
