"""
搜索相关模型
"""
from sqlalchemy import Column, String, Text, JSON

from .base import BaseModel


class SearchResult(BaseModel):
    """
    搜索结果模型
    用于存储搜索服务返回的结果，支持按URL去重
    """
    __tablename__ = 'search_results'
    
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
