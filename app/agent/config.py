"""
Configuration management for Agent Application
All settings are loaded from .env file
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from functools import lru_cache
from datetime import datetime, timezone

# 加载根目录的 .env 文件
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class Settings:
    """Agent 应用配置类"""
    
    # Agent Service 配置
    AGENT_SERVICE_PORT: int = int(os.getenv("AGENT_SERVICE_PORT", "8009"))
    AGENT_SERVICE_HOST: str = os.getenv("AGENT_SERVICE_HOST", "0.0.0.0")
    AGENT_SERVICE_DEBUG: bool = os.getenv("AGENT_SERVICE_DEBUG", "true").lower() == "true"
    
    # PostgreSQL 数据库配置
    PGSQL_HOST: str = os.getenv("PGSQL_HOST", "127.0.0.1")
    PGSQL_PORT: int = int(os.getenv("PGSQL_PORT", "5432"))
    PGSQL_USER: str = os.getenv("PGSQL_USER", "postgres")
    PGSQL_PASSWORD: str = os.getenv("PGSQL_PASSWORD", "postgres123")
    PGSQL_DATABASE: str = os.getenv("PGSQL_DATABASE", "myagent")
    
    # Agent LLM 配置（独立配置，优先于全局 LLM 配置）
    @property
    def AGENT_LLM_MODEL_NAME(self) -> str:
        """Agent 专用模型名称"""
        return os.getenv("AGENT_LLM_MODEL_NAME") or os.getenv("LLM_MODEL_NAME", "")
    
    @property
    def AGENT_LLM_URL(self) -> str:
        """Agent 专用 LLM API 地址"""
        return os.getenv("AGENT_LLM_URL") or os.getenv("LLM_URL", "")
    
    @property
    def AGENT_LLM_API_KEY(self) -> str:
        """Agent 专用 LLM API 密钥"""
        return os.getenv("AGENT_LLM_API_KEY") or os.getenv("LLM_API_KEY", "")
    
    # 全局 LLM 配置
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "")
    LLM_URL: str = os.getenv("LLM_URL", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    
    # Agent 参数配置
    DEFAULT_TEMPERATURE: float = float(os.getenv("AGENT_DEFAULT_TEMPERATURE", "0.3"))
    DEFAULT_MAX_TOKENS: int = int(os.getenv("AGENT_DEFAULT_MAX_TOKENS", "4096"))
    DEFAULT_TOP_P: float = float(os.getenv("AGENT_DEFAULT_TOP_P", "0.9"))
    
    # Agent 执行参数
    MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))
    ITERATION_TIMEOUT: int = int(os.getenv("AGENT_ITERATION_TIMEOUT", "120"))
    
    # 上下文配置
    MAX_CONTEXT_MESSAGES: int = int(os.getenv("AGENT_MAX_CONTEXT_MESSAGES", "50"))
    MAX_CONTEXT_TOKENS: int = int(os.getenv("AGENT_MAX_CONTEXT_TOKENS", "16000"))
    
    # Sandbox 服务配置
    SANDBOX_SERVICE_HOST: str = os.getenv("SANDBOX_SERVICE_HOST", "sandbox_service")
    SANDBOX_SERVICE_PORT: int = int(os.getenv("SANDBOX_SERVICE_PORT", "8010"))
    
    # Skills 配置
    SKILLS_DIRECTORY: str = os.getenv("SKILLS_DIRECTORY", "/app/services")
    SKILLS_AUTO_DISCOVER: bool = os.getenv("SKILLS_AUTO_DISCOVER", "true").lower() == "true"
    
    @property
    def sandbox_service_url(self) -> str:
        """构建 Sandbox 服务 URL"""
        return f"http://{self.SANDBOX_SERVICE_HOST}:{self.SANDBOX_SERVICE_PORT}"
    
    @property
    def database_url(self) -> str:
        """构建数据库连接URL"""
        return f"postgresql+psycopg2://{self.PGSQL_USER}:{self.PGSQL_PASSWORD}@{self.PGSQL_HOST}:{self.PGSQL_PORT}/{self.PGSQL_DATABASE}"
    
    @property
    def async_database_url(self) -> str:
        """构建异步数据库连接URL"""
        return f"postgresql+asyncpg://{self.PGSQL_USER}:{self.PGSQL_PASSWORD}@{self.PGSQL_HOST}:{self.PGSQL_PORT}/{self.PGSQL_DATABASE}"
    
    @staticmethod
    def get_current_date_info() -> dict:
        """获取当前日期信息（用于系统提示词）"""
        now = datetime.now(timezone.utc)
        return {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "timestamp": now.isoformat()
        }


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
