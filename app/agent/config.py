"""
Agent Service Configuration
Environment variables and settings
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class Settings(BaseSettings):
    """Agent 服务配置"""
    
    # Agent 服务配置
    AGENT_SERVICE_PORT: int = int(os.getenv("AGENT_SERVICE_PORT", "8020"))
    AGENT_SERVICE_HOST: str = os.getenv("AGENT_SERVICE_HOST", "0.0.0.0")
    AGENT_SERVICE_DEBUG: bool = os.getenv("AGENT_SERVICE_DEBUG", "true").lower() == "true"
    
    # Agent LLM 配置（优先使用 Agent 专用配置，否则回退到全局 LLM 配置）
    AGENT_LLM_MODEL_NAME: str = os.getenv(
        "AGENT_LLM_MODEL_NAME", 
        os.getenv("LLM_MODEL_NAME", "")
    )
    AGENT_LLM_URL: str = os.getenv(
        "AGENT_LLM_URL",
        os.getenv("LLM_URL", "")
    )
    AGENT_LLM_API_KEY: str = os.getenv(
        "AGENT_LLM_API_KEY",
        os.getenv("LLM_API_KEY", "")
    )
    
    # LLM 配置别名 (供 vlm_service 等使用)
    @property
    def LLM_MODEL_NAME(self) -> str:
        return self.AGENT_LLM_MODEL_NAME
    
    @property
    def LLM_URL(self) -> str:
        return self.AGENT_LLM_URL
    
    @property
    def LLM_API_KEY(self) -> str:
        return self.AGENT_LLM_API_KEY
    
    # VLM 视觉语言模型配置 (已弃用，保留用于兼容)
    VLM_MODEL_NAME: str = os.getenv("VLM_MODEL_NAME", "qwen3-vl-32b-instruct")
    VLM_URL: str = os.getenv(
        "VLM_URL",
        os.getenv("LLM_URL", "")
    )
    VLM_API_KEY: str = os.getenv(
        "VLM_API_KEY",
        os.getenv("LLM_API_KEY", "")
    )
    
    # Agent 参数配置
    AGENT_MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))
    AGENT_MAX_CONTEXT_TOKENS: int = int(os.getenv("AGENT_MAX_CONTEXT_TOKENS", "16000"))
    AGENT_DEFAULT_TEMPERATURE: float = float(os.getenv("AGENT_DEFAULT_TEMPERATURE", "0.7"))
    AGENT_DEFAULT_MAX_TOKENS: int = int(os.getenv("AGENT_DEFAULT_MAX_TOKENS", "4096"))
    
    # 并发控制配置
    AGENT_MAX_CONCURRENT_REQUESTS: int = int(os.getenv("AGENT_MAX_CONCURRENT_REQUESTS", "10"))
    AGENT_REQUEST_TIMEOUT: int = int(os.getenv("AGENT_REQUEST_TIMEOUT", "300"))  # 5分钟
    AGENT_LLM_CALL_TIMEOUT: int = int(os.getenv("AGENT_LLM_CALL_TIMEOUT", "30"))  # 30秒
    AGENT_TOOL_TIMEOUT: int = int(os.getenv("AGENT_TOOL_TIMEOUT", "60"))  # 工具执行超时60秒
    
    # 数据库配置（复用全局配置）
    PGSQL_HOST: str = os.getenv("PGSQL_HOST", "127.0.0.1")
    PGSQL_PORT: int = int(os.getenv("PGSQL_PORT", "5432"))
    PGSQL_USER: str = os.getenv("PGSQL_USER", "postgres")
    PGSQL_PASSWORD: str = os.getenv("PGSQL_PASSWORD", "postgres123")
    PGSQL_DATABASE: str = os.getenv("PGSQL_DATABASE", "myagent")
    
    @property
    def DATABASE_URL(self) -> str:
        """PostgreSQL 数据库连接 URL"""
        return f"postgresql://{self.PGSQL_USER}:{self.PGSQL_PASSWORD}@{self.PGSQL_HOST}:{self.PGSQL_PORT}/{self.PGSQL_DATABASE}"
    
    # 注意：各服务（sandbox/websearch/deepsearch/rag/embedding/rerank）的
    # HOST/PORT 配置不再需要在这里定义，各服务的 client.py 自己从 .env 读取
    
    class Config:
        env_file = ".env"
        extra = "ignore"


# 全局配置实例
settings = Settings()
