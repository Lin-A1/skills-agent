"""
URL 质量评分模块

职责：
- URL 质量评估（评分 0.0-1.0）
- 黑名单管理（严格黑名单/软黑名单）
- 权威来源识别

从 analyzer.py 提取，遵循单一职责原则。
"""
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class URLScorer:
    """URL 质量评分器"""
    
    # 严格黑名单域名（广告/付费墙/低质量内容源）- 完全过滤
    STRICT_BLACKLIST_DOMAINS = frozenset([
        # 文库/付费墙类
        "360doc.com", "docin.com", "doc88.com", "wenku.baidu.com",
        # 视频平台（通常内容不适合文本提取）
        "bilibili.com", "youku.com", "iqiyi.com", "ixigua.com",
        # 社交媒体
        "weibo.com", "weixin.qq.com", "mp.weixin.qq.com",
        # 问答类（通常质量参差不齐）
        "tieba.baidu.com", "zhidao.baidu.com", "wenwen.sogou.com", "wenda.so.com",
        # 新闻门户（首页通常无实质内容）
        "toutiao.com", "toutiaocdn.com",
    ])
    
    # 软黑名单域名（技术社区/博客）- 降权处理而非完全过滤
    SOFT_BLACKLIST_DOMAINS = frozenset([
        "zhihu.com", "zhuanlan.zhihu.com",
        "csdn.net", "blog.csdn.net",
        "jianshu.com",
        "bokeyuan.cn",
        "sohu.com", "163.com", "sina.com.cn",
    ])
    
    # 权威来源域名（高质量加分）
    AUTHORITATIVE_DOMAINS = frozenset([
        "gov.cn", ".edu.cn", ".edu", ".ac.cn",
        "wikipedia.org", "baike.baidu.com", "baike.sogou.com",
        "developer.mozilla.org", "docs.python.org", "docs.microsoft.com",
        "developer.apple.com", "cloud.google.com/docs",
        "github.com", "gitlab.com", "gitee.com",
        "arxiv.org", "scholar.google.com", "cnki.net",
        "engineering.fb.com", "ai.google", "openai.com/blog",
    ])
    
    # URL 路径黑名单（登录/广告/无效页）
    BLACKLIST_URL_PATTERNS = frozenset([
        "/login", "/signin", "/register", "/signup",
        "/ad/", "/ads/", "/advert", "/banner",
        "/cart", "/checkout", "/payment",
        "/404", "/error", "/not-found",
        "?ref=", "?utm_", "?from=",
    ])
    
    # 黑名单域名前缀
    BLACKLIST_DOMAIN_PREFIXES = frozenset(["bbs.", "forum."])
    
    def score(self, url: str, title: str = "") -> float:
        """
        评估 URL 质量
        
        Args:
            url: 待评估的 URL
            title: 页面标题（可选，用于垃圾内容检测）
            
        Returns:
            质量评分 0.0-1.0
        """
        score = 0.5
        url_lower = url.lower()
        title_lower = (title or "").lower()
        
        # 1. 权威来源加分
        for domain in self.AUTHORITATIVE_DOMAINS:
            if domain in url_lower:
                score += 0.35
                break
        
        # 2. 百科类特殊加分
        if "baike." in url_lower or "wikipedia." in url_lower:
            score += 0.25
        
        # 3. URL 路径质量检测
        for pattern in self.BLACKLIST_URL_PATTERNS:
            if pattern in url_lower:
                score -= 0.3
                break
        
        # 4. 软黑名单域名降权
        if self.is_soft_blacklisted(url):
            if "zhuanlan.zhihu.com" in url_lower:
                score -= 0.08  # 知乎专栏质量通常较高
            elif "blog.csdn.net" in url_lower:
                score -= 0.12  # CSDN 博客质量参差不齐
            else:
                score -= 0.15
        
        # 5. 标题质量评估
        if title:
            if 10 < len(title) < 80:
                score += 0.1
            spam_keywords = ["震惊", "必看", "速看", "转发", "点击", "免费", "限时"]
            if any(kw in title_lower for kw in spam_keywords):
                score -= 0.2
        
        # 6. URL 特征加分
        if "/docs/" in url_lower or "/documentation/" in url_lower:
            score += 0.15
        if "/api/" in url_lower and ("reference" in url_lower or "doc" in url_lower):
            score += 0.1
        
        return min(1.0, max(0.0, score))
    
    def is_blacklisted(self, url: str) -> bool:
        """
        检查 URL 是否在严格黑名单中
        
        软黑名单（技术社区）不在此处过滤，改为在评分阶段降权
        """
        url_lower = url.lower()
        
        try:
            parsed = urlparse(url_lower)
            domain = parsed.netloc
            
            # 检查域名前缀（bbs., forum.）
            for prefix in self.BLACKLIST_DOMAIN_PREFIXES:
                if domain.startswith(prefix):
                    return True
            
            # 只检查严格黑名单
            for blacklisted in self.STRICT_BLACKLIST_DOMAINS:
                if blacklisted in domain:
                    return True
        except Exception:
            pass
        
        # 检查 URL 路径黑名单
        for pattern in self.BLACKLIST_URL_PATTERNS:
            if pattern in url_lower:
                return True
        
        return False
    
    def is_soft_blacklisted(self, url: str) -> bool:
        """检查 URL 是否在软黑名单中（技术社区/博客类）"""
        url_lower = url.lower()
        try:
            parsed = urlparse(url_lower)
            domain = parsed.netloc
            for blacklisted in self.SOFT_BLACKLIST_DOMAINS:
                if blacklisted in domain:
                    return True
        except Exception:
            pass
        return False
    
    def is_authoritative(self, url: str) -> bool:
        """检查 URL 是否来自权威来源"""
        url_lower = url.lower()
        for domain in self.AUTHORITATIVE_DOMAINS:
            if domain in url_lower:
                return True
        return False
