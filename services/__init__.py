
"""微服务模块

包含所有微服务的客户端封装。
"""
from .ocr_service.client import *
from .embedding_service.client import *
from .rerank_service.client import *


__all__ = [
    "OCRServiceClient",
    "EmbeddingServiceClient",
    "RerankServiceClient",
]
