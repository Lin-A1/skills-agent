from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    """搜索请求模型"""
    query: str = Field(..., description="搜索关键词", min_length=1, max_length=200)
    max_results: int = Field(5, description="最大结果数量", ge=1, le=20)
    force_refresh: bool = Field(False, description="是否强制刷新（忽略缓存）")


class VLMAnalysisData(BaseModel):
    """LLM 分析结果数据（名称保留 VLM 以兼容旧版本）"""
    title_summary: str = Field(..., description="页面标题总结（简洁明了）", max_length=100)
    main_content: str = Field(..., description="主要内容概述（200-400字）", max_length=500)
    key_information: List[str] = Field(..., description="关键信息点（结构化要点）", min_length=1, max_length=8)
    credibility: str = Field(..., description="可信度: authoritative/commercial/forum/unknown")
    relevance_score: float = Field(..., description="与查询的相关性评分(0-1)", ge=0.0, le=1.0)
    cacheable: bool = Field(True, description="是否适合缓存（时效性内容应为false）")



class SearchResult(BaseModel):
    """单个搜索结果"""
    index: int = Field(..., description="结果索引")
    title: str = Field(..., description="页面标题")
    url: str = Field(..., description="页面URL")
    source_domain: str = Field("", description="来源域名")
    data: Optional[VLMAnalysisData] = Field(None, description="LLM 分析数据")
    success: bool = Field(..., description="是否成功分析")
    error_message: str = Field("", description="错误信息")
    timestamp: str = Field("", description="抓取时间戳")
    from_cache: bool = Field(False, description="是否来自缓存")
    
    @property
    def relevance_score(self) -> float:
        """便捷访问相关性评分"""
        return self.data.relevance_score if self.data else 0.0
    
    @property
    def credibility(self) -> str:
        """便捷访问可信度"""
        return self.data.credibility if self.data else "unknown"


class ChatRequest(BaseModel):
    """聊天请求模型"""
    messages: List[Dict[str, str]] = Field(..., description="消息列表")
    model: str = Field("qwen-plus", description="模型名称")
    stream: bool = Field(True, description="是否流式返回")


class SearchResponse(BaseModel):
    """搜索响应模型"""
    query: str = Field(..., description="搜索关键词")
    total: int = Field(..., description="返回结果总数")
    success_count: int = Field(..., description="成功分析的数量")
    cached_count: int = Field(0, description="来自缓存的数量")
    results: List[SearchResult] = Field(..., description="搜索结果列表")
    search_timestamp: str = Field("", description="搜索时间戳")
