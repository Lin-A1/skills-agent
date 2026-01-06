"""
Milvus 向量数据库连接配置
"""
from pymilvus import connections, utility
import os
import logging

logger = logging.getLogger(__name__)

# 全局连接状态
_connected = False
_alias = "default"


def get_connection_params():
    """从环境变量获取 Milvus 连接参数"""
    return {
        "host": os.getenv("MILVUS_HOST", "127.0.0.1"),
        "port": os.getenv("MILVUS_PORT", "19530"),
        "user": os.getenv("MILVUS_USER", ""),
        "password": os.getenv("MILVUS_PASSWORD", ""),
    }


def init_milvus(alias: str = "default") -> bool:
    """
    初始化 Milvus 连接
    
    Args:
        alias: 连接别名
        
    Returns:
        是否连接成功
    """
    global _connected, _alias
    
    if _connected:
        return True
    
    params = get_connection_params()
    
    try:
        connect_params = {
            "alias": alias,
            "host": params["host"],
            "port": params["port"],
        }
        
        # 如果配置了用户名密码
        if params["user"] and params["password"]:
            connect_params["user"] = params["user"]
            connect_params["password"] = params["password"]
        
        connections.connect(**connect_params)
        _connected = True
        _alias = alias
        
        logger.info(f"Milvus 连接成功: {params['host']}:{params['port']}")
        return True
        
    except Exception as e:
        logger.error(f"Milvus 连接失败: {e}")
        return False


def disconnect_milvus(alias: str = "default"):
    """断开 Milvus 连接"""
    global _connected
    
    try:
        connections.disconnect(alias)
        _connected = False
        logger.info("Milvus 连接已断开")
    except Exception as e:
        logger.warning(f"断开 Milvus 连接时出错: {e}")


def is_connected() -> bool:
    """检查是否已连接"""
    return _connected


def get_alias() -> str:
    """获取当前连接别名"""
    return _alias


def list_collections() -> list:
    """列出所有集合"""
    if not _connected:
        init_milvus()
    return utility.list_collections()
