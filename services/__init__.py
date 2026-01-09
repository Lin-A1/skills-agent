"""微服务模块

包含所有微服务的客户端封装。
使用 try-except 导入以支持不同环境下的按需加载。
"""

# 默认导出列表
__all__ = []

# OCR 服务客户端
try:
    from .ocr_service.client import OCRServiceClient
    __all__.append("OCRServiceClient")
except ImportError:
    pass

# Embedding 服务客户端
try:
    from .embedding_service.client import EmbeddingServiceClient
    __all__.append("EmbeddingServiceClient")
except ImportError:
    pass

# Rerank 服务客户端
try:
    from .rerank_service.client import RerankServiceClient
    __all__.append("RerankServiceClient")
except ImportError:
    pass

# File Service 客户端
try:
    from .file_service.client import FileServiceClient
    __all__.append("FileServiceClient")
except ImportError:
    pass
