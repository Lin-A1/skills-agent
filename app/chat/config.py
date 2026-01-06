"""
Configuration management for Chat Application
All settings are loaded from .env file
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from functools import lru_cache

# 加载根目录的 .env 文件
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class Settings:
    """应用配置类"""
    
    # Chat Service 配置
    CHAT_SERVICE_PORT: int = int(os.getenv("CHAT_SERVICE_PORT", "8006"))
    CHAT_SERVICE_HOST: str = os.getenv("CHAT_SERVICE_HOST", "0.0.0.0")
    CHAT_SERVICE_DEBUG: bool = os.getenv("CHAT_SERVICE_DEBUG", "true").lower() == "true"
    
    # PostgreSQL 数据库配置
    PGSQL_HOST: str = os.getenv("PGSQL_HOST", "127.0.0.1")
    PGSQL_PORT: int = int(os.getenv("PGSQL_PORT", "5432"))
    PGSQL_USER: str = os.getenv("PGSQL_USER", "postgres")
    PGSQL_PASSWORD: str = os.getenv("PGSQL_PASSWORD", "postgres123")
    PGSQL_DATABASE: str = os.getenv("PGSQL_DATABASE", "myagent")
    
    # Chat LLM 配置（独立配置，优先于全局LLM配置）
    # 如果CHAT_LLM_*未设置，则回退到全局LLM_*配置
    @property
    def CHAT_LLM_MODEL_NAME(self) -> str:
        """Chat专用模型名称"""
        return os.getenv("CHAT_LLM_MODEL_NAME") or os.getenv("LLM_MODEL_NAME", "")
    
    @property
    def CHAT_LLM_URL(self) -> str:
        """Chat专用LLM API地址"""
        return os.getenv("CHAT_LLM_URL") or os.getenv("LLM_URL", "")
    
    @property
    def CHAT_LLM_API_KEY(self) -> str:
        """Chat专用LLM API密钥"""
        return os.getenv("CHAT_LLM_API_KEY") or os.getenv("LLM_API_KEY", "")
    
    # 全局 LLM 配置（保留向后兼容）
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "")
    LLM_URL: str = os.getenv("LLM_URL", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    
    # 聊天参数默认值
    DEFAULT_TEMPERATURE: float = float(os.getenv("CHAT_DEFAULT_TEMPERATURE", "0.7"))
    DEFAULT_MAX_TOKENS: int = int(os.getenv("CHAT_DEFAULT_MAX_TOKENS", "2048"))
    DEFAULT_TOP_P: float = float(os.getenv("CHAT_DEFAULT_TOP_P", "0.9"))
    
    # 上下文配置
    MAX_CONTEXT_MESSAGES: int = int(os.getenv("CHAT_MAX_CONTEXT_MESSAGES", "20"))
    MAX_CONTEXT_TOKENS: int = int(os.getenv("CHAT_MAX_CONTEXT_TOKENS", "8000"))
    
    @property
    def database_url(self) -> str:
        """构建数据库连接URL"""
        return f"postgresql://{self.PGSQL_USER}:{self.PGSQL_PASSWORD}@{self.PGSQL_HOST}:{self.PGSQL_PORT}/{self.PGSQL_DATABASE}"
    
    @property
    def async_database_url(self) -> str:
        """构建异步数据库连接URL"""
        return f"postgresql+asyncpg://{self.PGSQL_USER}:{self.PGSQL_PASSWORD}@{self.PGSQL_HOST}:{self.PGSQL_PORT}/{self.PGSQL_DATABASE}"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
