"""
RAG 多路检索服务

核心特性：
1. 向量语义检索 (Milvus)
2. 多路混合检索
3. Rerank 重排序
4. 统一检索接口

支持被 WebSearch/DeepSearch 服务调用
"""
import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pymilvus import connections, Collection, utility

# 加载环境变量
load_dotenv()

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===== 请求/响应模型 =====
class RetrieveRequest(BaseModel):
    """检索请求"""
    query: str = Field(..., description="查询文本", min_length=1, max_length=500)
    collection_name: str = Field("websearch_results", description="集合名称")
    top_k: int = Field(5, description="返回结果数量", ge=1, le=50)
    min_score: float = Field(0.85, description="最小相似度阈值", ge=0, le=1)
    rerank: bool = Field(True, description="是否进行重排序")


class RetrieveResult(BaseModel):
    """单条检索结果"""
    id: str = Field(..., description="文档ID")
    text: str = Field(..., description="文档内容")
    score: float = Field(..., description="相似度得分")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class RetrieveResponse(BaseModel):
    """检索响应"""
    query: str = Field(..., description="原始查询")
    results: List[RetrieveResult] = Field(default_factory=list, description="检索结果")
    total: int = Field(0, description="结果总数")
    elapsed_ms: float = Field(0, description="耗时(毫秒)")
    from_cache: bool = Field(False, description="是否命中缓存")


class SaveRequest(BaseModel):
    """保存请求"""
    collection_name: str = Field("websearch_results", description="集合名称")
    documents: List[Dict[str, Any]] = Field(..., description="文档列表")


class SaveResponse(BaseModel):
    """保存响应"""
    saved_count: int = Field(0, description="保存的文档数")
    collection_name: str = Field(..., description="集合名称")


# ===== RAG 检索引擎 =====
class RAGEngine:
    """RAG 多路检索引擎"""
    
    COLLECTION_NAME = "websearch_results"
    EMBEDDING_DIM = 1024
    
    def __init__(self):
        # Milvus 配置
        self.milvus_host = os.getenv("MILVUS_HOST", "milvus")
        self.milvus_port = os.getenv("MILVUS_PORT", "19530")
        
        # Embedding 服务配置
        self.embedding_host = os.getenv("EMBEDDING_HOST", "embedding_service")
        self.embedding_port = os.getenv("EMBEDDING_PORT", "8002")
        self.embedding_url = f"http://{self.embedding_host}:{self.embedding_port}"
        
        # Rerank 服务配置
        self.rerank_host = os.getenv("RERANK_HOST", "rerank_service")
        self.rerank_port = os.getenv("RERANK_PORT", "8003")
        self.rerank_url = f"http://{self.rerank_host}:{self.rerank_port}"
        
        # 状态
        self._milvus_connected = False
        self._embedding_available = False
        self._rerank_available = False
        
        # 持久化 HTTP 客户端（连接池复用）
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )
        
        # 缓存 (query -> (timestamp, results))
        self._cache: Dict[str, tuple] = {}
        self.CACHE_TTL = 300  # 5 分钟
        self.CACHE_MAX_SIZE = 100
        
        logger.info(f"RAG Engine 配置 - Milvus: {self.milvus_host}:{self.milvus_port}")
    
    def initialize(self) -> bool:
        """初始化连接"""
        try:
            # 连接 Milvus
            connections.connect(
                alias="default",
                host=self.milvus_host,
                port=self.milvus_port
            )
            self._milvus_connected = True
            logger.info(f"Milvus 连接成功: {self.milvus_host}:{self.milvus_port}")
        except Exception as e:
            logger.error(f"Milvus 连接失败: {e}")
            self._milvus_connected = False
        
        return self._milvus_connected
    
    async def check_services(self):
        """检查依赖服务可用性"""
        # 检查 Embedding 服务
        try:
            resp = await self.http_client.get(f"{self.embedding_url}/health", timeout=5.0)
            self._embedding_available = resp.status_code == 200
        except Exception as e:
            logger.debug(f"Embedding 服务检查失败: {e}")
            self._embedding_available = False
        
        # 检查 Rerank 服务
        try:
            resp = await self.http_client.get(f"{self.rerank_url}/health", timeout=5.0)
            self._rerank_available = resp.status_code == 200
        except Exception as e:
            logger.debug(f"Rerank 服务检查失败: {e}")
            self._rerank_available = False
        
        logger.info(f"服务状态 - Embedding: {self._embedding_available}, Rerank: {self._rerank_available}")
    
    async def embed_query(self, query: str) -> List[float]:
        """生成查询向量"""
        resp = await self.http_client.post(
            f"{self.embedding_url}/v1/embeddings",
            json={
                "model": os.getenv("EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B"),
                "input": [query]
            }
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]
    
    async def rerank(self, query: str, documents: List[str], top_n: int = 5) -> List[int]:
        """重排序，返回排序后的索引"""
        if not self._rerank_available or not documents:
            return list(range(min(top_n, len(documents))))
        
        try:
            resp = await self.http_client.post(
                f"{self.rerank_url}/rerank",
                json={
                    "query": query,
                    "documents": documents,
                    "top_n": top_n
                }
            )
            resp.raise_for_status()
            data = resp.json()
            return [r["index"] for r in data.get("results", [])]
        except Exception as e:
            logger.warning(f"Rerank 失败: {e}")
            return list(range(min(top_n, len(documents))))
    
    def _get_cache_key(self, query: str, collection: str, top_k: int) -> str:
        """生成缓存 key"""
        return f"{query.strip().lower()}|{collection}|{top_k}"
    
    def _get_cached(self, cache_key: str) -> Optional[List[RetrieveResult]]:
        """获取缓存"""
        if cache_key in self._cache:
            timestamp, results = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self.CACHE_TTL:
                return results
            del self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, results: List[RetrieveResult]):
        """设置缓存"""
        if len(self._cache) >= self.CACHE_MAX_SIZE:
            oldest = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest]
        self._cache[cache_key] = (datetime.now(), results)
    
    async def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        """
        执行检索
        
        流程：
        1. 检查缓存
        2. 生成查询向量
        3. Milvus 向量检索
        4. 过滤低分结果
        5. Rerank 重排序
        6. 返回结果
        """
        start_time = datetime.now()
        cache_key = self._get_cache_key(request.query, request.collection_name, request.top_k)
        
        # 1. 检查缓存
        cached = self._get_cached(cache_key)
        if cached:
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"缓存命中: '{request.query[:30]}...'")
            return RetrieveResponse(
                query=request.query,
                results=cached,
                total=len(cached),
                elapsed_ms=elapsed,
                from_cache=True
            )
        
        # 2. 检查 Milvus 连接
        if not self._milvus_connected:
            return RetrieveResponse(query=request.query, results=[], total=0)
        
        try:
            # 3. 生成查询向量
            query_vector = await self.embed_query(request.query)
            
            # 4. 获取集合
            if not utility.has_collection(request.collection_name):
                logger.warning(f"集合 '{request.collection_name}' 不存在")
                return RetrieveResponse(query=request.query, results=[], total=0)
            
            collection = Collection(request.collection_name)
            collection.load()
            
            # 5. 向量搜索（直接获取 text，避免二次查询）
            search_k = request.top_k * 2 if request.rerank else request.top_k
            
            results = collection.search(
                data=[query_vector],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {}},
                limit=search_k,
                output_fields=["metadata", "text"]  # 一次性获取所有需要的字段
            )
            
            if not results or not results[0]:
                logger.warning(f"Milvus 返回空结果: query='{request.query[:30]}'")
                return RetrieveResponse(query=request.query, results=[], total=0)
            
            logger.info(f"Milvus 原始结果: {len(results[0])} 条")
            
            # 6. 过滤并构建候选列表（无需二次查询）
            candidates = []
            for hit in results[0]:
                # Milvus 返回的 distance 等于 Cosine Similarity
                score = hit.distance
                if score >= request.min_score:
                    candidates.append({
                        "id": str(hit.id),
                        "text": hit.entity.get("text", ""),
                        "score": score,
                        "metadata": hit.entity.get("metadata", {})
                    })
            
            logger.info(f"过滤后候选: {len(candidates)} 条 (阈值={request.min_score})")
            if not candidates:
                return RetrieveResponse(query=request.query, results=[], total=0)
            
            # 7. Rerank 重排序
            if request.rerank and len(candidates) > request.top_k:
                docs = [c["text"] for c in candidates]
                rerank_indices = await self.rerank(request.query, docs, request.top_k)
                candidates = [candidates[i] for i in rerank_indices if i < len(candidates)]
            else:
                candidates = candidates[:request.top_k]
            
            # 8. 构建结果
            final_results = [
                RetrieveResult(
                    id=c["id"],
                    text=c["text"],
                    score=c["score"],
                    metadata=c["metadata"]
                )
                for c in candidates
            ]
            
            # 9. 缓存结果
            self._set_cache(cache_key, final_results)
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"检索完成: '{request.query[:30]}...' -> {len(final_results)} 条结果, {elapsed:.0f}ms")
            
            return RetrieveResponse(
                query=request.query,
                results=final_results,
                total=len(final_results),
                elapsed_ms=elapsed,
                from_cache=False
            )
            
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return RetrieveResponse(query=request.query, results=[], total=0)
    
    async def save(self, request: SaveRequest) -> SaveResponse:
        """保存文档到向量数据库"""
        if not self._milvus_connected:
            return SaveResponse(saved_count=0, collection_name=request.collection_name)
        
        saved = 0
        for doc in request.documents:
            try:
                text = doc.get("text", "")
                if not text:
                    continue
                
                # 生成向量
                embedding = await self.embed_query(text)
                
                # 获取集合
                collection = Collection(request.collection_name)
                
                # [OPTIMIZATION] 使用全文哈希生成 ID，避免前缀相同的内容产生冲突
                doc_id = hashlib.md5(text.encode()).hexdigest()[:16]
                
                collection.insert([{
                    "id": doc_id,
                    "text": text[:5000],
                    "embedding": embedding,
                    "metadata": doc.get("metadata", {})
                }])
                saved += 1
                
            except Exception as e:
                logger.warning(f"保存文档失败: {e}")
        
        if saved > 0:
            logger.info(f"保存 {saved} 条文档到 '{request.collection_name}'")
        
        return SaveResponse(saved_count=saved, collection_name=request.collection_name)
    
    async def close(self):
        """关闭连接"""
        try:
            await self.http_client.aclose()
        except Exception as e:
            logger.debug(f"关闭 HTTP 客户端失败: {e}")
        try:
            connections.disconnect("default")
        except Exception as e:
            logger.debug(f"断开 Milvus 连接失败: {e}")


# ===== FastAPI 应用 =====
engine: Optional[RAGEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    global engine
    
    engine = RAGEngine()
    engine.initialize()
    await engine.check_services()
    logger.info("RAG 服务启动成功")
    
    yield
    
    if engine:
        await engine.close()
    logger.info("RAG 服务已关闭")


app = FastAPI(
    title="RAG 多路检索服务",
    description="基于向量数据库的语义检索服务，支持多路检索和重排序",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "RAG Service",
        "version": "1.0.0",
        "features": [
            "向量语义检索",
            "Rerank 重排序",
            "结果缓存",
            "多集合支持"
        ]
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    if engine:
        await engine.check_services()
    
    return {
        "status": "healthy" if engine and engine._milvus_connected else "degraded",
        "service": "rag",
        "milvus_connected": engine._milvus_connected if engine else False,
        "embedding_available": engine._embedding_available if engine else False,
        "rerank_available": engine._rerank_available if engine else False,
        "cache_size": len(engine._cache) if engine else 0
    }


@app.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(request: RetrieveRequest):
    """
    语义检索
    
    - **query**: 查询文本
    - **collection_name**: 集合名称
    - **top_k**: 返回结果数量
    - **min_score**: 最小相似度阈值
    - **rerank**: 是否进行重排序
    """
    if not engine:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    return await engine.retrieve(request)


@app.post("/save", response_model=SaveResponse)
async def save(request: SaveRequest):
    """
    保存文档到向量数据库
    
    - **collection_name**: 集合名称
    - **documents**: 文档列表，每个文档包含 text 和 metadata
    """
    if not engine:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    return await engine.save(request)


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("RAG_SERVICE_PORT", "8008"))
    
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
