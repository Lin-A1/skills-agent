"""
PostgreSQL 客户端
提供增删改查的封装接口
"""
from typing import List, Dict, Any, Optional, Type
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from contextlib import contextmanager
import logging

from .models import Base
from .database import get_session, init_db

logger = logging.getLogger(__name__)


class PgSQLClient:
    """PostgreSQL 数据库客户端"""
    
    def __init__(self):
        """初始化客户端"""
        self.initialized = False
    
    def initialize(self):
        """初始化数据库连接"""
        if not self.initialized:
            init_db()
            self.initialized = True
            logger.info("PostgreSQL client initialized")
    
    @contextmanager
    def get_db_session(self):
        """获取数据库会话的上下文管理器"""
        if not self.initialized:
            self.initialize()
        
        session = get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def create(self, model_class: Type[Base], data: Dict[str, Any]) -> Optional[Base]:
        """
        创建记录
        
        Args:
            model_class: 模型类
            data: 数据字典
            
        Returns:
            创建的对象实例
        """
        with self.get_db_session() as session:
            try:
                instance = model_class(**data)
                session.add(instance)
                session.flush()
                session.refresh(instance)
                return instance
            except Exception as e:
                logger.error(f"Create error: {e}")
                raise
    
    def bulk_create(self, model_class: Type[Base], data_list: List[Dict[str, Any]]) -> List[Base]:
        """
        批量创建记录
        
        Args:
            model_class: 模型类
            data_list: 数据字典列表
            
        Returns:
            创建的对象实例列表
        """
        with self.get_db_session() as session:
            try:
                instances = [model_class(**data) for data in data_list]
                session.add_all(instances)
                session.flush()
                for instance in instances:
                    session.refresh(instance)
                return instances
            except Exception as e:
                logger.error(f"Bulk create error: {e}")
                raise
    
    def get(self, model_class: Type[Base], record_id: int) -> Optional[Base]:
        """
        根据ID获取单条记录
        
        Args:
            model_class: 模型类
            record_id: 记录ID
            
        Returns:
            对象实例或None
        """
        with self.get_db_session() as session:
            return session.query(model_class).filter(
                model_class.id == record_id,
                model_class.is_deleted == False
            ).first()
    
    def filter(self, model_class: Type[Base], filters: Dict[str, Any] = None,
               limit: int = None, offset: int = None, order_by: str = None,
               as_dict: bool = True) -> List:
        """
        查询记录列表
        
        Args:
            model_class: 模型类
            filters: 过滤条件字典
            limit: 限制返回数量
            offset: 偏移量
            order_by: 排序字段（如 'created_at' 或 '-created_at' 表示降序）
            as_dict: 是否返回字典列表（默认True，避免会话关闭后无法访问属性）
            
        Returns:
            字典列表或对象实例列表
        """
        with self.get_db_session() as session:
            query = session.query(model_class).filter(model_class.is_deleted == False)
            
            # 应用过滤条件
            if filters:
                for key, value in filters.items():
                    if hasattr(model_class, key):
                        query = query.filter(getattr(model_class, key) == value)
            
            # 排序
            if order_by:
                if order_by.startswith('-'):
                    query = query.order_by(getattr(model_class, order_by[1:]).desc())
                else:
                    query = query.order_by(getattr(model_class, order_by))
            
            # 分页
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            results = query.all()
            
            # 转换为字典以避免会话关闭后无法访问
            if as_dict:
                return [r.to_dict() for r in results]
            
            # 如果需要对象，分离后返回
            for r in results:
                session.expunge(r)
            return results
    
    def update(self, model_class: Type[Base], record_id: int, data: Dict[str, Any]) -> Optional[Base]:
        """
        更新记录
        
        Args:
            model_class: 模型类
            record_id: 记录ID
            data: 更新的数据字典
            
        Returns:
            更新后的对象实例
        """
        with self.get_db_session() as session:
            instance = session.query(model_class).filter(
                model_class.id == record_id,
                model_class.is_deleted == False
            ).first()
            
            if not instance:
                return None
            
            for key, value in data.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            session.flush()
            session.refresh(instance)
            return instance
    
    def delete(self, model_class: Type[Base], record_id: int, soft_delete: bool = True) -> bool:
        """
        删除记录
        
        Args:
            model_class: 模型类
            record_id: 记录ID
            soft_delete: 是否软删除（默认True）
            
        Returns:
            是否删除成功
        """
        with self.get_db_session() as session:
            instance = session.query(model_class).filter(
                model_class.id == record_id
            ).first()
            
            if not instance:
                return False
            
            if soft_delete:
                instance.is_deleted = True
            else:
                session.delete(instance)
            
            return True
    
    def count(self, model_class: Type[Base], filters: Dict[str, Any] = None) -> int:
        """
        统计记录数量
        
        Args:
            model_class: 模型类
            filters: 过滤条件字典
            
        Returns:
            记录数量
        """
        with self.get_db_session() as session:
            query = session.query(model_class).filter(model_class.is_deleted == False)
            
            if filters:
                for key, value in filters.items():
                    if hasattr(model_class, key):
                        query = query.filter(getattr(model_class, key) == value)
            
            return query.count()
    
    def execute_raw_sql(self, sql: str, params: Dict[str, Any] = None) -> List[Dict]:
        """
        执行原生SQL查询
        
        Args:
            sql: SQL语句
            params: 参数字典
            
        Returns:
            查询结果列表
        """
        with self.get_db_session() as session:
            result = session.execute(sql, params or {})
            return [dict(row) for row in result]


# 全局客户端实例
_client = None


def get_pgsql_client() -> PgSQLClient:
    """获取全局PostgreSQL客户端实例"""
    global _client
    if _client is None:
        _client = PgSQLClient()
        _client.initialize()
    return _client
