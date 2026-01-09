"""
搜索结果过滤模块

职责：
- 结果质量过滤
- 相关性排序
- 域名去重

从 analyzer.py 提取，遵循单一职责原则。
"""
import logging
from typing import List

from .models import SearchResult

logger = logging.getLogger(__name__)


class ResultFilter:
    """搜索结果过滤器"""
    
    def __init__(
        self,
        min_relevance_score: float = 0.5,
        max_same_domain_results: int = 2
    ):
        """
        Args:
            min_relevance_score: 最低相关性评分阈值
            max_same_domain_results: 同域名最大结果数
        """
        self.min_relevance_score = min_relevance_score
        self.max_same_domain_results = max_same_domain_results
    
    def filter_by_quality(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        根据质量过滤结果
        
        保留：
        - 成功分析且相关性评分达标的结果
        - 来自缓存的结果（已经过验证）
        """
        filtered = []
        for r in results:
            if r.success and r.data and r.data.relevance_score >= self.min_relevance_score:
                filtered.append(r)
            elif r.from_cache:
                filtered.append(r)
        return filtered
    
    def sort_by_relevance(self, results: List[SearchResult]) -> List[SearchResult]:
        """按相关性评分降序排序"""
        def sort_key(r: SearchResult):
            if r.data:
                return (1 if r.success else 0, r.data.relevance_score)
            return (0, 0)
        
        return sorted(results, key=sort_key, reverse=True)
    
    def dedupe_by_domain(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        域名去重：限制同一域名的结果数量
        
        避免搜索结果被单一网站主导
        """
        domain_count = {}
        deduped = []
        
        for r in results:
            domain = r.source_domain or "unknown"
            count = domain_count.get(domain, 0)
            if count < self.max_same_domain_results:
                deduped.append(r)
                domain_count[domain] = count + 1
        
        return deduped
    
    def process(
        self,
        results: List[SearchResult],
        max_results: int = 5
    ) -> List[SearchResult]:
        """
        完整的过滤流程
        
        1. 质量过滤
        2. 相关性排序
        3. 域名去重
        4. 截取指定数量
        5. 重新编号
        """
        # 过滤
        filtered = self.filter_by_quality(results)
        
        # 排序
        sorted_results = self.sort_by_relevance(filtered)
        
        # 去重
        deduped = self.dedupe_by_domain(sorted_results)
        
        # 截取
        final = deduped[:max_results]
        
        # 重新编号
        for idx, result in enumerate(final, 1):
            result.index = idx
        
        return final
