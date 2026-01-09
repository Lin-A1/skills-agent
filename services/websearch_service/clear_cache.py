import os
import sys
import logging
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

def clear_postgres_cache():
    logger.info("正在清理 PostgreSQL 缓存...")
    try:
        from storage.pgsql.client import get_pgsql_client
        from storage.pgsql.models.search import SearchResult
        
        # 获取客户端
        client = get_pgsql_client()
        # 初始化数据库连接（如果不显式调用 initialize，get_db_session 也会尝试初始化）
        client.initialize()
        
        # 使用 get_db_session 获取会话
        with client.get_db_session() as session:
            count = session.query(SearchResult).delete()
            # 注意: get_db_session 上下文管理器会自动 commit
            logger.info(f"PostgreSQL: 已删除 {count} 条搜索记录")
            
    except Exception as e:
        logger.error(f"PostgreSQL 清理失败: {e}")

def clear_milvus_cache():
    logger.info("正在清理 Milvus 向量缓存...")
    try:
        from storage.milvus.client import get_milvus_client
        
        # Milvus 集合名称
        COLLECTION_NAME = "websearch_results"
        
        client = get_milvus_client()
        # 初始化连接
        client.initialize()
        
        # 直接调用封装好的 drop_collection
        if client.drop_collection(COLLECTION_NAME):
            logger.info(f"Milvus: 已删除集合 {COLLECTION_NAME}")
        else:
            logger.info(f"Milvus: 删除集合 {COLLECTION_NAME} 失败或集合不存在")

    except Exception as e:
        logger.error(f"Milvus 清理失败: {e}")

if __name__ == "__main__":
    clear_postgres_cache()
    clear_milvus_cache()
    logger.info("清理完成！")
