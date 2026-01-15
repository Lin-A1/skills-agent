"""
PostgreSQL 数据库连接配置
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from .models import Base

# 全局引擎和会话工厂
engine = None
SessionLocal = None


def get_database_url():
    """从环境变量获取数据库连接URL"""
    user = os.getenv('PGSQL_USER', 'postgres')
    password = os.getenv('PGSQL_PASSWORD', 'postgres')
    host = os.getenv('PGSQL_HOST', 'localhost')
    port = os.getenv('PGSQL_PORT', '5432')
    database = os.getenv('PGSQL_DATABASE', 'myagent')
    
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def init_db():
    """初始化数据库连接"""
    global engine, SessionLocal
    
    database_url = get_database_url()
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    return engine


def get_session():
    """获取数据库会话"""
    if SessionLocal is None:
        init_db()
    return SessionLocal()
