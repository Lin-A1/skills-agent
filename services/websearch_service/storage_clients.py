import logging
import hashlib
from typing import List, Dict
from urllib.parse import urlparse

from .models import SearchResult, VLMAnalysisData

logger = logging.getLogger(__name__)

class SearchCacheManager:
    """搜索结果缓存管理器（使用 PostgreSQL）"""
    
    def __init__(self):
        self._db_client = None
        self._initialized = False
        self._model_class = None
    
    def initialize(self):
        """初始化数据库连接"""
        if self._initialized:
            return True
        
        try:
            from storage.pgsql.client import get_pgsql_client
            from storage.pgsql.models import SearchResult as DBSearchResult
            
            self._db_client = get_pgsql_client()
            self._model_class = DBSearchResult
            self._initialized = True
            logger.info("数据库缓存管理器初始化成功")
            return True
        except Exception as e:
            logger.warning(f"数据库缓存初始化失败（将禁用缓存）: {e}")
            return False
    
    @property
    def is_available(self) -> bool:
        """缓存是否可用"""
        return self._initialized and self._db_client is not None
    
    def _normalize_url(self, url: str) -> str:
        """标准化URL用于去重比较"""
        try:
            parsed = urlparse(url)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            return normalized.lower()
        except Exception:
            return url.lower()
    
    def search_cache(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """从数据库缓存中搜索结果"""
        if not self.is_available:
            return []
        
        try:
            results = self._db_client.filter(
                self._model_class,
                filters={"query": query},
                limit=max_results,
                order_by="-created_at"
            )
            
            cached_results = []
            for idx, r in enumerate(results, 1):
                extra_data = r.get("extra_data", {}) or {}
                
                # 重建 VLMAnalysisData
                vlm_data = None
                if extra_data.get("key_information"):
                    try:
                        vlm_data = VLMAnalysisData(
                            title_summary=r.get("snippet") or "",
                            main_content=r.get("content") or "",
                            key_information=extra_data.get("key_information", []),
                            credibility=extra_data.get("credibility", "unknown"),
                            relevance_score=float(extra_data.get("relevance_score", 0.5))
                        )
                    except Exception as e:
                        logger.debug(f"重建 VLMAnalysisData 失败: {e}")
                
                cached_results.append(SearchResult(
                    index=idx,
                    title=r.get("title") or "",
                    url=r.get("url") or "",
                    source_domain=r.get("source") or "",
                    data=vlm_data,
                    success=extra_data.get("success", True),
                    timestamp=extra_data.get("timestamp", ""),
                    from_cache=True
                ))
            
            return cached_results
        except Exception as e:
            logger.warning(f"从数据库查询缓存失败: {e}")
            return []
    
    def save_results(self, query: str, results: List[SearchResult]) -> int:
        """将搜索结果保存到数据库（自动去重）"""
        if not self.is_available or not results:
            return 0
        
        urls_to_check = [r.url for r in results if r.url and not r.from_cache]
        if not urls_to_check:
            return 0
        
        existing_urls = self._get_existing_urls(urls_to_check)
        
        saved_count = 0
        for result in results:
            if result.from_cache or not result.url:
                continue
            if not result.data or not result.success:
                logger.debug(f"跳过无效结果 (data为空或失败): {result.url}")
                continue
            
            normalized_url = self._normalize_url(result.url)
            if normalized_url in existing_urls:
                logger.debug(f"URL已存在，跳过: {result.url}")
                continue
            
            try:
                data = {
                    "query": query,
                    "url": result.url,
                    "title": result.title,
                    "snippet": result.data.title_summary if result.data else "",
                    "content": result.data.main_content if result.data else "",
                    "source": result.source_domain,
                    "extra_data": {
                        "key_information": result.data.key_information if result.data else [],
                        "credibility": result.data.credibility if result.data else "unknown",
                        "relevance_score": result.data.relevance_score if result.data else 0.0,
                        "timestamp": result.timestamp,
                        "success": result.success
                    }
                }
                
                self._db_client.create(self._model_class, data)
                existing_urls.add(normalized_url)
                saved_count += 1
                logger.debug(f"保存搜索结果: {result.url}")
            except Exception as e:
                logger.warning(f"保存搜索结果失败 {result.url}: {e}")
        
        if saved_count > 0:
            logger.info(f"共保存 {saved_count} 条新搜索结果到缓存")
        return saved_count
    
    def _get_existing_urls(self, urls_to_check: List[str]) -> set:
        """检查哪些 URL 已存在于数据库中"""
        if not self.is_available or not urls_to_check:
            return set()
        
        try:
            normalized_urls = [self._normalize_url(u) for u in urls_to_check]
            results = self._db_client.filter(
                self._model_class,
                filters={"url__in": normalized_urls},
                limit=len(normalized_urls)
            )
            return {self._normalize_url(r.get("url")) for r in results if r.get("url")}
        except Exception as e:
            logger.warning(f"获取已存在URL失败: {e}")
            return set()


class VectorCacheManager:
    """向量缓存管理器（使用 Milvus + Embedding Service）"""
    
    COLLECTION_NAME = "websearch_results"
    
    def __init__(self):
        self._milvus_client = None
        self._embedding_client = None
        self._rerank_client = None
        self._initialized = False
        self._vector_dim = 1024  # Qwen3-Embedding 输出维度
    
    def initialize(self) -> bool:
        """初始化向量存储连接"""
        if self._initialized:
            return True
        
        try:
            from storage.milvus.client import get_milvus_client
            from services.embedding_service.client import EmbeddingServiceClient
            from services.rerank_service.client import RerankServiceClient
            
            self._milvus_client = get_milvus_client(default_dim=self._vector_dim)
            self._embedding_client = EmbeddingServiceClient()
            self._rerank_client = RerankServiceClient()
            
            # 创建集合（如不存在）
            self._milvus_client.create_collection(
                self.COLLECTION_NAME,
                schema_type="text_embedding"
            )
            
            # 创建索引
            self._milvus_client.create_index(
                self.COLLECTION_NAME,
                field_name="embedding",
                index_type="IVF_FLAT",
                metric_type="COSINE"
            )
            
            self._initialized = True
            logger.info("向量缓存管理器初始化成功")
            return True
        except Exception as e:
            logger.warning(f"向量缓存初始化失败（将禁用向量搜索）: {e}")
            return False
    
    @property
    def is_available(self) -> bool:
        """向量缓存是否可用"""
        return self._initialized and self._milvus_client is not None
    
    def semantic_search(self, query: str, top_k: int = 5, min_score: float = 0.85, rerank: bool = True) -> List[Dict]:
        """语义搜索：通过向量相似度查找相关结果，并可选进行重排序"""
        if not self.is_available:
            return []
        
        try:
            # 生成查询向量
            query_vector = self._embedding_client.embed_query(query)
            
            # 向量搜索 (获取更多候选用于重排序)
            search_k = top_k * 2 if rerank else top_k
            
            results = self._milvus_client.search(
                self.COLLECTION_NAME,
                query_vectors=[query_vector],
                top_k=search_k,
                output_fields=["text", "metadata"]
            )
            
            if not results or not results[0]:
                return []
            
            # 过滤低分结果
            candidates = []
            for hit in results[0]:
                # Milvus 的 score 可能是距离或相似度
                if hit.get("score", 0) >= min_score:
                    candidates.append({
                        "id": hit.get("id"),
                        "score": hit.get("score", 0),
                        "text": hit.get("text", ""),
                        "metadata": hit.get("metadata", {})
                    })
            
            if not candidates:
                return []
                
            # 如果不需要重排序，或者候选数量少于等于 top_k，直接返回
            if not rerank or len(candidates) <= top_k:
                return candidates[:top_k]
            
            # 执行 Rerank
            try:
                logger.info(f"对 {len(candidates)} 个向量检索结果进行重排序")
                docs = [c["text"] for c in candidates]
                rerank_indices = self._rerank_client.get_top_indices(query, docs, top_n=top_k)
                
                final_results = []
                for idx in rerank_indices:
                    final_results.append(candidates[idx])
                return final_results
            except Exception as e:
                logger.warning(f"Rerank 失败，回退到原始顺序: {e}")
                return candidates[:top_k]
                
        except Exception as e:
            logger.warning(f"向量语义搜索失败: {e}")
            return []
    
    def save_results(self, results: List[SearchResult]) -> int:
        """将搜索结果保存到向量数据库"""
        if not self.is_available or not results:
            return 0
        
        saved_count = 0
        for result in results:
            # 跳过无效结果
            if result.from_cache or not result.data or not result.success:
                continue
            
            # 确保 main_content 有实际内容
            if not result.data.main_content or len(result.data.main_content.strip()) < 50:
                logger.debug(f"跳过内容过短的结果: {result.url}")
                continue
            
            try:
                # [OPTIMIZATION] 向量化使用 Title + Summary，提高语义匹配准确度
                # 之前仅使用 Title，容易导致语义信息不足
                summary = result.data.title_summary if result.data.title_summary else result.data.main_content[:200]
                embed_text = f"{result.title}\n{summary}"
                
                # 存储使用 Title + Content (保留上下文)
                storage_text = f"{result.title}\n{result.data.main_content}"
                
                # 生成向量
                embedding = self._embedding_client.embed_query(embed_text)
                
                # 生成唯一ID（基于URL的hash）
                doc_id = hashlib.md5(result.url.encode()).hexdigest()[:16]
                
                # 准备元数据
                metadata = {
                    "url": result.url,
                    "title": result.title,
                    "source_domain": result.source_domain,
                    "credibility": result.data.credibility,
                    "relevance_score": result.data.relevance_score,
                    "key_information": result.data.key_information[:3] if result.data.key_information else []
                }
                
                # 插入向量数据库
                self._milvus_client.insert(
                    self.COLLECTION_NAME,
                    data=[{
                        "id": doc_id,
                        "text": storage_text[:5000],  # 存储全文
                        "embedding": embedding,
                        "metadata": metadata
                    }]
                )
                saved_count += 1
            except Exception as e:
                logger.warning(f"保存向量失败 {result.url}: {e}")
        
        if saved_count > 0:
            logger.info(f"共保存 {saved_count} 条搜索结果到向量数据库")
        return saved_count
