"""
Sandbox 服务客户端
"""
import os
from typing import Optional, Dict, Any
from pathlib import Path

import requests
from dotenv import load_dotenv

# 加载 .env
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class SandboxClient:
    """沙盒服务客户端"""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 60.0):
        """
        初始化客户端

        Args:
            base_url: 服务地址，默认从环境变量读取
            timeout: 请求超时时间（秒）
        """
        if base_url is None:
            host = os.getenv("SANDBOX_SERVICE_HOST", "127.0.0.1")
            port = os.getenv("SANDBOX_SERVICE_PORT", "8009")
            base_url = f"http://{host}:{port}"

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def execute(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
        env_vars: Optional[Dict[str, str]] = None,
        trusted_mode: bool = False,
        workspace_mount_path: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行代码

        Args:
            code: 要执行的代码
            language: 编程语言 (python/shell/bash)
            timeout: 超时时间（秒）
            env_vars: 环境变量
            trusted_mode: 信任模式 - 允许访问 services 模块和网络
                          开启后可以 from services.xxx.client import ...
            workspace_mount_path: 工作区挂载路径 (e.g. /home/user/workspace)
            session_id: 会话ID，用于隔离工作区。如果提供，将挂载 workspace_mount_path/session_id

        Returns:
            dict: 执行结果，包含 success, stdout, stderr, exit_code, execution_time
        """
        url = f"{self.base_url}/execute"
        payload = {
            "code": code,
            "language": language,
            "trusted_mode": trusted_mode
        }
        if timeout is not None:
            payload["timeout"] = timeout
        if env_vars is not None:
            payload["env_vars"] = env_vars
        if workspace_mount_path is not None:
            payload["workspace_mount_path"] = workspace_mount_path
        if session_id is not None:
            payload["session_id"] = session_id
        
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        url = f"{self.base_url}/health"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    # 使用示例
    client = SandboxClient()
    
    # 健康检查
    print("健康检查:", client.health_check())

    # 执行 Python 代码
    result = client.execute("print('Hello, Sandbox!')", language="python")
    print(f"\nPython 执行结果:")
    print(f"  成功: {result['success']}")
    print(f"  输出: {result['stdout']}")
    print(f"  耗时: {result['execution_time']}s")
    
    # 执行 Shell 命令
    result = client.execute("echo 'Hello from Shell' && date", language="shell")
    print(f"\nShell 执行结果:")
    print(f"  成功: {result['success']}")
    print(f"  输出: {result['stdout']}")
