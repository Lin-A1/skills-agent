"""
Milvus 向量数据库客户端
提供向量存储的增删改查接口
"""
from typing import List, Dict, Any, Optional, Union
from pymilvus import (
    Collection, 
    CollectionSchema, 
    FieldSchema, 
    DataType,
    utility,
    connections
)
import logging

from .database import init_milvus, is_connected, get_alias

logger = logging.getLogger(__name__)


# 预定义的常用 Schema
COMMON_SCHEMAS = {
    "text_embedding": {
        "fields": [
            {"name": "id", "dtype": DataType.VARCHAR, "is_primary": True, "max_length": 64},
            {"name": "text", "dtype": DataType.VARCHAR, "max_length": 65535},
            {"name": "embedding", "dtype": DataType.FLOAT_VECTOR, "dim": 1024},
            {"name": "metadata", "dtype": DataType.JSON},
        ],
        "description": "文本向量存储"
    },
    "document_chunk": {
        "fields": [
            {"name": "id", "dtype": DataType.VARCHAR, "is_primary": True, "max_length": 64},
            {"name": "doc_id", "dtype": DataType.VARCHAR, "max_length": 64},
            {"name": "chunk_index", "dtype": DataType.INT64},
            {"name": "content", "dtype": DataType.VARCHAR, "max_length": 65535},
            {"name": "embedding", "dtype": DataType.FLOAT_VECTOR, "dim": 1024},
            {"name": "metadata", "dtype": DataType.JSON},
        ],
        "description": "文档分块向量存储"
    }
}


class MilvusClient:
    """Milvus 向量数据库客户端"""
    
    def __init__(self, default_dim: int = 1024):
        """
        初始化客户端
        
        Args:
            default_dim: 默认向量维度
        """
        self.default_dim = default_dim
        self.initialized = False
    
    def initialize(self) -> bool:
        """初始化连接"""
        if not self.initialized:
            self.initialized = init_milvus()
        return self.initialized
    
    def _ensure_connected(self):
        """确保已连接"""
        if not is_connected():
            self.initialize()
    
    def create_collection(
        self,
        collection_name: str,
        schema_type: str = None,
        fields: List[Dict] = None,
        dim: int = None,
        description: str = ""
    ) -> Optional[Collection]:
        """
        创建集合
        
        Args:
            collection_name: 集合名称
            schema_type: 预定义 schema 类型 (text_embedding/document_chunk)
            fields: 自定义字段列表（与 schema_type 二选一）
            dim: 向量维度（覆盖默认值）
            description: 集合描述
            
        Returns:
            Collection 对象
        """
        self._ensure_connected()
        
        # 检查是否已存在
        if utility.has_collection(collection_name):
            logger.info(f"集合 '{collection_name}' 已存在")
            return Collection(collection_name)
        
        # 使用预定义 schema
        if schema_type and schema_type in COMMON_SCHEMAS:
            schema_config = COMMON_SCHEMAS[schema_type]
            fields = schema_config["fields"]
            description = description or schema_config["description"]
        
        if not fields:
            # 默认 schema
            fields = [
                {"name": "id", "dtype": DataType.VARCHAR, "is_primary": True, "max_length": 64},
                {"name": "embedding", "dtype": DataType.FLOAT_VECTOR, "dim": dim or self.default_dim},
                {"name": "metadata", "dtype": DataType.JSON},
            ]
        
        # 构建 FieldSchema 列表
        field_schemas = []
        for field in fields:
            field_params = {
                "name": field["name"],
                "dtype": field["dtype"],
            }
            if field.get("is_primary"):
                field_params["is_primary"] = True
            if field.get("max_length"):
                field_params["max_length"] = field["max_length"]
            if field["dtype"] == DataType.FLOAT_VECTOR:
                field_params["dim"] = field.get("dim", dim or self.default_dim)
            
            field_schemas.append(FieldSchema(**field_params))
        
        schema = CollectionSchema(fields=field_schemas, description=description)
        collection = Collection(name=collection_name, schema=schema)
        
        logger.info(f"创建集合 '{collection_name}' 成功")
        return collection
    
    def get_collection(self, collection_name: str) -> Optional[Collection]:
        """获取集合"""
        self._ensure_connected()
        
        if not utility.has_collection(collection_name):
            logger.warning(f"集合 '{collection_name}' 不存在")
            return None
        
        return Collection(collection_name)
    
    def drop_collection(self, collection_name: str) -> bool:
        """删除集合"""
        self._ensure_connected()
        
        if utility.has_collection(collection_name):
            utility.drop_collection(collection_name)
            logger.info(f"删除集合 '{collection_name}' 成功")
            return True
        return False
    
    def list_collections(self) -> List[str]:
        """列出所有集合"""
        self._ensure_connected()
        return utility.list_collections()
    
    def insert(
        self,
        collection_name: str,
        data: List[Dict[str, Any]],
        create_if_not_exists: bool = True
    ) -> Optional[List]:
        """
        插入向量数据
        
        Args:
            collection_name: 集合名称
            data: 数据列表，每个元素为字典
            create_if_not_exists: 集合不存在时是否自动创建
            
        Returns:
            插入的 ID 列表
        """
        self._ensure_connected()
        
        collection = self.get_collection(collection_name)
        if collection is None:
            if create_if_not_exists:
                collection = self.create_collection(collection_name)
            else:
                return None
        
        try:
            # 转换数据格式
            if data:
                fields = list(data[0].keys())
                insert_data = [[item[field] for item in data] for field in fields]
                
                result = collection.insert(insert_data)
                collection.flush()
                
                logger.info(f"插入 {len(data)} 条数据到 '{collection_name}'")
                return result.primary_keys
        except Exception as e:
            logger.error(f"插入数据失败: {e}")
            raise
        
        return None
    
    def search(
        self,
        collection_name: str,
        query_vectors: List[List[float]],
        vector_field: str = "embedding",
        top_k: int = 10,
        output_fields: List[str] = None,
        filter_expr: str = None,
        metric_type: str = "COSINE"
    ) -> List[List[Dict]]:
        """
        向量相似度搜索
        
        Args:
            collection_name: 集合名称
            query_vectors: 查询向量列表
            vector_field: 向量字段名
            top_k: 返回最相似的 K 条
            output_fields: 返回的字段列表
            filter_expr: 过滤表达式
            metric_type: 距离度量类型 (COSINE/L2/IP)
            
        Returns:
            搜索结果列表
        """
        self._ensure_connected()
        
        collection = self.get_collection(collection_name)
        if collection is None:
            return []
        
        # 加载集合到内存
        collection.load()
        
        search_params = {
            "metric_type": metric_type,
            "params": {"nprobe": 10}
        }
        
        try:
            results = collection.search(
                data=query_vectors,
                anns_field=vector_field,
                param=search_params,
                limit=top_k,
                output_fields=output_fields,
                expr=filter_expr
            )
            
            # 转换为字典格式
            formatted_results = []
            for hits in results:
                hit_list = []
                for hit in hits:
                    hit_dict = {
                        "id": hit.id,
                        "distance": hit.distance,
                        "score": 1 - hit.distance if metric_type == "COSINE" else hit.distance
                    }
                    if output_fields:
                        for field in output_fields:
                            hit_dict[field] = hit.entity.get(field)
                    hit_list.append(hit_dict)
                formatted_results.append(hit_list)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []
    
    def delete(
        self,
        collection_name: str,
        ids: List[str] = None,
        filter_expr: str = None
    ) -> bool:
        """
        删除向量
        
        Args:
            collection_name: 集合名称
            ids: 要删除的 ID 列表
            filter_expr: 过滤表达式（与 ids 二选一）
            
        Returns:
            是否成功
        """
        self._ensure_connected()
        
        collection = self.get_collection(collection_name)
        if collection is None:
            return False
        
        try:
            if ids:
                expr = f'id in {ids}'
            elif filter_expr:
                expr = filter_expr
            else:
                return False
            
            collection.delete(expr)
            logger.info(f"从 '{collection_name}' 删除数据成功")
            return True
            
        except Exception as e:
            logger.error(f"删除数据失败: {e}")
            return False
    
    def get_by_ids(
        self,
        collection_name: str,
        ids: List[str],
        output_fields: List[str] = None
    ) -> List[Dict]:
        """
        根据 ID 获取数据
        
        Args:
            collection_name: 集合名称
            ids: ID 列表
            output_fields: 返回的字段列表
            
        Returns:
            数据列表
        """
        self._ensure_connected()
        
        collection = self.get_collection(collection_name)
        if collection is None:
            return []
        
        try:
            collection.load()
            expr = f'id in {ids}'
            results = collection.query(expr=expr, output_fields=output_fields)
            return results
            
        except Exception as e:
            logger.error(f"查询数据失败: {e}")
            return []
    
    def create_index(
        self,
        collection_name: str,
        field_name: str = "embedding",
        index_type: str = "IVF_FLAT",
        metric_type: str = "COSINE",
        params: Dict = None
    ) -> bool:
        """
        创建索引
        
        Args:
            collection_name: 集合名称
            field_name: 字段名
            index_type: 索引类型 (IVF_FLAT/IVF_SQ8/HNSW)
            metric_type: 距离度量类型
            params: 索引参数
            
        Returns:
            是否成功
        """
        self._ensure_connected()
        
        collection = self.get_collection(collection_name)
        if collection is None:
            return False
        
        index_params = {
            "index_type": index_type,
            "metric_type": metric_type,
            "params": params or {"nlist": 1024}
        }
        
        try:
            collection.create_index(field_name, index_params)
            logger.info(f"创建索引 '{field_name}' @ '{collection_name}' 成功")
            return True
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            return False
    
    def count(self, collection_name: str) -> int:
        """获取集合中的数据数量"""
        self._ensure_connected()
        
        collection = self.get_collection(collection_name)
        if collection is None:
            return 0
        
        return collection.num_entities


# 全局客户端实例
_client = None


def get_milvus_client(default_dim: int = 1024) -> MilvusClient:
    """获取全局 Milvus 客户端实例"""
    global _client
    if _client is None:
        _client = MilvusClient(default_dim=default_dim)
        _client.initialize()
    return _client
