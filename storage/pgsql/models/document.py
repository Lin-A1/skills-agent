"""
文档相关模型
"""
from sqlalchemy import Column, String, Text, JSON

from .base import BaseModel


class Document(BaseModel):
    """文档模型"""
    __tablename__ = 'documents'
    
    title = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=True)
    extra_data = Column(JSON, nullable=True)
    source = Column(String(255), nullable=True)
