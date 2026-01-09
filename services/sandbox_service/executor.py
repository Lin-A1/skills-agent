"""
代码执行引擎
在隔离的 Docker 容器中安全执行代码
"""
import asyncio
import logging
import os
import tempfile
import textwrap
import uuid
from typing import Dict, Any, Optional, Literal
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Language(str, Enum):
    PYTHON = "python"
    SHELL = "shell"
    BASH = "bash"


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    error: Optional[str] = None


# 语言对应的 Docker 镜像和执行命令
LANGUAGE_CONFIG = {
    Language.PYTHON: {
        "image": "python:3.10-slim",
        "command": ["python", "-c"],
        "file_ext": ".py"
    },
    Language.SHELL: {
        "image": "alpine:latest",
        "command": ["sh", "-c"],
        "file_ext": ".sh"
    },
    Language.BASH: {
        "image": "bash:latest",
        "command": ["bash", "-c"],
        "file_ext": ".sh"
    }
}


class CodeExecutor:
    """代码执行器"""
    
    def __init__(self):
        self.timeout = int(os.getenv("SANDBOX_EXECUTION_TIMEOUT", "30"))
        self.memory_limit = os.getenv("SANDBOX_MEMORY_LIMIT", "256m")
        self.cpu_limit = os.getenv("SANDBOX_CPU_LIMIT", "1.0")
        
        logger.info(f"CodeExecutor 初始化: timeout={self.timeout}s, memory={self.memory_limit}, cpu={self.cpu_limit}")
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
        env_vars: Optional[Dict[str, str]] = None,
        trusted_mode: bool = False
    ) -> ExecutionResult:
        """
        执行代码
        
        Args:
            code: 要执行的代码
            language: 编程语言 (python/shell/bash)
            timeout: 超时时间（秒），默认使用配置值
            env_vars: 环境变量
            trusted_mode: 信任模式 - 允许访问 services 模块和网络
                          开启后可以 from services.xxx.client import ...
            
        Returns:
            ExecutionResult: 执行结果
        """
        import time
        start_time = time.time()
        
        # 规范化语言名称
        lang = self._normalize_language(language)
        if lang is None:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"不支持的语言: {language}",
                exit_code=-1,
                execution_time=0,
                error=f"Unsupported language: {language}"
            )
        
        config = LANGUAGE_CONFIG[lang]
        exec_timeout = timeout or self.timeout
        container_name = f"sandbox_{uuid.uuid4().hex[:12]}"

        
        # 预处理代码：去除公共前导空白和首尾空行
        code = textwrap.dedent(code).strip()
        
        try:
            # 构建 Docker 命令
            docker_cmd = self._build_docker_command(
                container_name=container_name,
                image=config["image"],
                command=config["command"],
                code=code,
                env_vars=env_vars,
                timeout=exec_timeout,
                trusted_mode=trusted_mode
            )

            
            logger.info(f"执行代码 [lang={lang.value}, container={container_name}]")
            logger.debug(f"Docker 命令: {' '.join(docker_cmd)}")
            
            # 执行 Docker 容器
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=exec_timeout + 5  # 额外 5 秒缓冲
                )
            except asyncio.TimeoutError:
                # 超时，强制终止容器
                await self._kill_container(container_name)
                execution_time = time.time() - start_time
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"执行超时（{exec_timeout}秒）",
                    exit_code=-1,
                    execution_time=execution_time,
                    error="Execution timeout"
                )
            
            execution_time = time.time() - start_time
            exit_code = process.returncode or 0
            
            return ExecutionResult(
                success=exit_code == 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=exit_code,
                execution_time=round(execution_time, 3)
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.exception(f"代码执行失败: {e}")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=execution_time,
                error=str(e)
            )
        finally:
            # 清理容器
            await self._cleanup_container(container_name)
    
    def _normalize_language(self, language: str) -> Optional[Language]:
        """规范化语言名称"""
        lang_lower = language.lower().strip()
        if lang_lower in ("python", "python3", "py"):
            return Language.PYTHON
        elif lang_lower in ("shell", "sh"):
            return Language.SHELL
        elif lang_lower == "bash":
            return Language.BASH
        return None
    
    def _build_docker_command(
        self,
        container_name: str,
        image: str,
        command: list,
        code: str,
        env_vars: Optional[Dict[str, str]],
        timeout: int,
        trusted_mode: bool = False
    ) -> list:
        """
        构建 Docker 执行命令
        
        Args:
            trusted_mode: 信任模式
                - False: 严格隔离（无网络、只读）
                - True: 允许访问 services 和网络
        """
        cmd = [
            "docker", "run",
            "--rm",                          # 执行后自动删除
            "--name", container_name,
            "--memory", self.memory_limit,   # 内存限制
            "--cpus", self.cpu_limit,        # CPU 限制
            "--security-opt", "no-new-privileges",  # 禁止提权
            "--pids-limit", "100",           # 进程数限制
        ]
        
        if trusted_mode:
            # 信任模式：允许访问服务和网络
            logger.info(f"[trusted_mode] 启用信任模式，允许访问 services 和网络")
            
            # 使用项目网络（myagent_network）
            cmd.extend(["--network", "myagent_network"])
            
            # 挂载 services 目录（只读）
            # 容器外路径需要是绝对路径
            services_path = os.getenv("SERVICES_MOUNT_PATH", "/app/services")
            cmd.extend(["-v", f"{services_path}:/app/services:ro"])
            
            # 挂载 .env 文件（让 services 能读取配置）
            env_path = os.getenv("ENV_FILE_PATH", "/app/.env")
            cmd.extend(["-v", f"{env_path}:/app/.env:ro"])
            
            # 设置 PYTHONPATH
            cmd.extend(["-e", "PYTHONPATH=/app"])
            
            # 工作目录
            cmd.extend(["-w", "/app"])
            
            # 使用预装依赖的镜像
            image = os.getenv("SANDBOX_TRUSTED_IMAGE", "python:3.10-slim")
            
            # 允许可写临时目录
            cmd.extend(["--tmpfs", "/tmp:rw,size=128m"])
        else:
            # 隔离模式：严格安全限制
            cmd.extend([
                "--network", "none",         # 禁用网络
                "--read-only",               # 只读文件系统
                "--user", "nobody",          # 非 root 用户
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            ])
        
        # 添加环境变量
        if env_vars:
            for key, value in env_vars.items():
                # 安全过滤环境变量名
                if key.isidentifier():
                    cmd.extend(["-e", f"{key}={value}"])
        
        # 镜像和执行命令
        cmd.append(image)
        cmd.extend(command)
        cmd.append(code)
        
        return cmd

    
    async def _kill_container(self, container_name: str):
        """强制终止容器"""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "kill", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(process.wait(), timeout=5)
        except Exception as e:
            logger.warning(f"终止容器失败 {container_name}: {e}")
    
    async def _cleanup_container(self, container_name: str):
        """清理容器（如果还存在）"""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(process.wait(), timeout=5)
        except Exception:
            pass  # 忽略清理错误
    
    async def check_docker_available(self) -> bool:
        """检查 Docker 是否可用"""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(process.wait(), timeout=10)
            return process.returncode == 0
        except Exception:
            return False
    
    async def pull_base_images(self):
        """预拉取基础镜像"""
        for lang, config in LANGUAGE_CONFIG.items():
            image = config["image"]
            logger.info(f"拉取镜像: {image}")
            try:
                process = await asyncio.create_subprocess_exec(
                    "docker", "pull", image,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.wait()
            except Exception as e:
                logger.warning(f"拉取镜像失败 {image}: {e}")
