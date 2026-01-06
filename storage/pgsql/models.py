"""
PostgreSQL ORM 模型定义
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

# 创建基类
Base = declarative_base()


class BaseModel(Base):
    """基础模型类，包含公共字段"""
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    def to_dict(self):
        """将模型转换为字典"""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Document(BaseModel):
    """文档模型示例"""
    __tablename__ = 'documents'
    
    title = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=True)
    extra_data = Column(JSON, nullable=True)
    source = Column(String(255), nullable=True)


class SearchHistory(BaseModel):
    """搜索历史模型示例"""
    __tablename__ = 'search_history'
    
    query = Column(String(500), nullable=False)
    results = Column(JSON, nullable=True)
    user_id = Column(String(100), nullable=True, index=True)
    search_type = Column(String(50), nullable=True)


class WebSearchResult(BaseModel):
    """
    网络搜索结果模型
    用于存储搜索服务返回的结果，支持按URL去重
    """
    __tablename__ = 'web_search_results'
    
    # 搜索关键词
    query = Column(String(500), nullable=False, index=True)
    # 结果URL（用于去重）
    url = Column(String(2048), nullable=False, unique=True, index=True)
    # 结果标题
    title = Column(String(500), nullable=True)
    # 结果摘要/内容
    snippet = Column(Text, nullable=True)
    # 完整内容（如果有）
    content = Column(Text, nullable=True)
    # 来源/域名
    source = Column(String(255), nullable=True)
    # 额外元数据
    extra_data = Column(JSON, nullable=True)
