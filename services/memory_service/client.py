"""
Memory Service Client
提供语义化的记忆检索能力，让 Agent 自主决定何时检索历史对话
"""
import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MemoryServiceClient:
    """
    记忆服务客户端
    
    提供三种主要能力：
    1. search: 语义搜索相关记忆
    2. get_recent: 获取最近的对话
    3. get_session_summary: 获取会话摘要
    """
    
    def __init__(self):
        """初始化客户端"""
        # 延迟导入避免循环依赖
        self._db = None
        self._embedding_client = None
        self._AgentMessage = None
        self._AgentSession = None
        logger.info("MemoryServiceClient initialized")
    
    @property
    def db(self):
        """获取数据库会话（懒加载）"""
        if self._db is None:
            from storage.pgsql.database import get_session
            self._db = get_session()
        return self._db
    
    @property
    def embedding_client(self):
        """获取 Rerank 客户端（懒加载）"""
        if self._embedding_client is None:
            try:
                from services.rerank_service.client import RerankServiceClient
                self._embedding_client = RerankServiceClient()
            except Exception as e:
                logger.warning(f"Failed to initialize rerank client: {e}")
                self._embedding_client = None
        return self._embedding_client
    
    @property
    def rerank_client(self):
        """获取 Rerank 客户端（别名）"""
        return self.embedding_client
    
    @property
    def llm_client(self):
        """获取 LLM 客户端（懒加载）"""
        if not hasattr(self, '_llm_client') or self._llm_client is None:
            try:
                from app.agent.services.llm_service import agent_llm_service
                self._llm_client = agent_llm_service
            except Exception as e:
                logger.warning(f"Failed to initialize LLM client: {e}")
                self._llm_client = None
        return self._llm_client
    
    @property
    def AgentMessage(self):
        if self._AgentMessage is None:
            from storage.pgsql.models import AgentMessage
            self._AgentMessage = AgentMessage
        return self._AgentMessage
    
    @property
    def AgentSession(self):
        if self._AgentSession is None:
            from storage.pgsql.models import AgentSession
            self._AgentSession = AgentSession
        return self._AgentSession
    
    def search(
        self,
        query: str,
        session_id: str,  # 必填：限定在当前会话内搜索
        user_id: str = "anonymous",
        limit: int = 5,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        语义搜索相关记忆（使用 Rerank + LLM 两阶段检索）
        
        注意：仅在当前会话内搜索，不会跨会话检索
        
        流程：
        1. 从数据库获取当前会话最近 50 条消息
        2. Rerank 模型初筛 → top 10 候选
        3. LLM 精选 + 整合 → 最相关的 N 条
        
        Args:
            query: 搜索查询（自然语言）
            session_id: 当前会话 ID（必填）
            user_id: 用户 ID
            limit: 返回数量限制
            days: 限定时间范围（最近 N 天）
            
        Returns:
            包含搜索结果的字典
        """
        if not session_id:
            return {
                "success": False,
                "error": "session_id is required for memory search",
                "results": [],
                "total": 0
            }
        
        try:
            # 构建基础查询 - 必须限定在当前会话内
            q = self.db.query(self.AgentMessage).join(
                self.AgentSession,
                self.AgentMessage.session_id == self.AgentSession.id
            ).filter(
                self.AgentSession.session_id == session_id,  # 必须限定会话
                self.AgentSession.user_id == user_id,
                self.AgentMessage.role.in_(["user", "assistant"])
            )
            
            # 限定时间范围
            if days:
                cutoff = datetime.utcnow() - timedelta(days=days)
                q = q.filter(self.AgentMessage.created_at >= cutoff)
            
            # 获取候选消息（按时间倒序，取最近的）
            candidates = q.order_by(self.AgentMessage.created_at.desc()).limit(50).all()
            
            if not candidates:
                return {"success": True, "results": [], "total": 0}
            
            # 两阶段检索：Rerank 初筛 + LLM 精选
            if self.rerank_client and len(candidates) > limit:
                results = self._two_stage_retrieval(query, candidates, limit)
            else:
                # 降级为简单关键词匹配 + 时间排序
                results = self._keyword_rank(query, candidates, limit)
            
            return {
                "success": True,
                "results": results,
                "total": len(results)
            }
            
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "total": 0
            }
    
    def _two_stage_retrieval(
        self,
        query: str,
        candidates: List[Any],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        两阶段检索：Rerank 初筛 + LLM 精选
        
        Stage 1: Rerank 从 50 条中选出 top 10
        Stage 2: LLM 从 10 条中做最终判断
        """
        try:
            # === Stage 1: Rerank 初筛 ===
            documents = []
            for i, c in enumerate(candidates):
                role_label = "用户" if c.role == "user" else "助手"
                doc_text = f"[{i}] [{role_label}] {c.content[:300]}"
                documents.append(doc_text)
            
            rerank_results = self.rerank_client.rerank(
                query=query,
                documents=documents,
                top_n=min(10, len(candidates))  # 初筛取 top 10
            )
            
            # 获取初筛结果
            stage1_candidates = []
            # 兼容 rerank 返回格式：可能是 {"results": [...]} 或直接是 [...]
            results_list = rerank_results.get("results", []) if isinstance(rerank_results, dict) else rerank_results
            
            for item in results_list:
                idx = item.get("index", 0)
                if idx < len(candidates):
                    stage1_candidates.append({
                        "msg": candidates[idx],
                        "rerank_score": item.get("relevance_score", 0)
                    })
            
            if not stage1_candidates:
                return self._keyword_rank(query, candidates, limit)
            
            # === Stage 2: LLM 精选 ===
            if self.llm_client and len(stage1_candidates) > limit:
                return self._llm_select(query, stage1_candidates, limit)
            else:
                # 如果没有 LLM，直接返回 Rerank 结果
                return self._format_results(stage1_candidates[:limit])
            
        except Exception as e:
            logger.warning(f"Two-stage retrieval failed: {e}")
            return self._keyword_rank(query, candidates, limit)
    
    async def _llm_select_async(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """LLM 异步精选"""
        # 构建候选列表
        candidates_text = []
        for i, c in enumerate(candidates):
            msg = c["msg"]
            role_label = "用户" if msg.role == "user" else "助手"
            time_str = msg.created_at.strftime("%m-%d %H:%M") if msg.created_at else "未知时间"
            candidates_text.append(f"{i+1}. [{time_str}] [{role_label}] {msg.content[:200]}")
        
        prompt = f"""从以下历史对话中，选择与查询最相关的 {limit} 条记录。

查询：{query}

候选记录：
{chr(10).join(candidates_text)}

请直接返回最相关记录的序号（用逗号分隔），例如：1,3,5
只返回序号，不要其他内容。"""

        try:
            response = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50
            )
            
            content = response.get("content", "")
            # 解析序号
            selected_indices = []
            for part in content.replace(" ", "").split(","):
                try:
                    idx = int(part.strip()) - 1  # 转为 0-indexed
                    if 0 <= idx < len(candidates):
                        selected_indices.append(idx)
                except ValueError:
                    continue
            
            if selected_indices:
                selected = [candidates[i] for i in selected_indices[:limit]]
                return self._format_results(selected)
            
        except Exception as e:
            logger.warning(f"LLM select failed: {e}")
        
        # 降级返回 Rerank 结果
        return self._format_results(candidates[:limit])
    
    def _llm_select(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """LLM 同步精选（包装异步方法）"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在异步上下文中，创建新任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._llm_select_async(query, candidates, limit)
                    )
                    return future.result(timeout=10)
            else:
                return loop.run_until_complete(
                    self._llm_select_async(query, candidates, limit)
                )
        except Exception as e:
            logger.warning(f"LLM select sync wrapper failed: {e}")
            return self._format_results(candidates[:limit])
    
    def _format_results(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """格式化返回结果"""
        results = []
        for c in candidates:
            msg = c["msg"]
            results.append({
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "session_id": str(msg.session_id),
                "relevance_score": round(c.get("rerank_score", 0), 3)
            })
        return results
    
    def _keyword_rank(
        self,
        query: str,
        candidates: List[Any],
        limit: int
    ) -> List[Dict[str, Any]]:
        """简单关键词匹配排序"""
        query_lower = query.lower()
        keywords = query_lower.split()
        
        scored = []
        for msg in candidates:
            content_lower = (msg.content or "").lower()
            # 计算关键词匹配分数
            score = sum(1 for kw in keywords if kw in content_lower)
            scored.append((msg, score))
        
        # 按匹配度和时间排序
        scored.sort(key=lambda x: (x[1], x[0].created_at), reverse=True)
        
        results = []
        for msg, score in scored[:limit]:
            results.append({
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "session_id": str(msg.session_id),
                "relevance_score": min(1.0, score / max(len(keywords), 1))
            })
        
        return results
    
    def get_recent(
        self,
        session_id: str,
        limit: int = 10,
        include_tool: bool = False
    ) -> Dict[str, Any]:
        """
        获取会话最近的消息
        
        Args:
            session_id: 会话 ID
            limit: 返回数量
            include_tool: 是否包含工具调用消息
            
        Returns:
            最近的消息列表
        """
        try:
            # 查找会话
            session = self.db.query(self.AgentSession).filter(
                self.AgentSession.session_id == session_id
            ).first()
            
            if not session:
                return {"success": False, "error": "Session not found", "results": []}
            
            # 构建查询
            roles = ["user", "assistant"]
            if include_tool:
                roles.append("tool")
            
            messages = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.session_id == session.id,
                self.AgentMessage.role.in_(roles)
            ).order_by(self.AgentMessage.created_at.desc()).limit(limit).all()
            
            # 反转为时间正序
            messages = list(reversed(messages))
            
            results = []
            for msg in messages:
                results.append({
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None
                })
            
            return {
                "success": True,
                "results": results,
                "total": len(results),
                "session_title": session.title
            }
            
        except Exception as e:
            logger.error(f"Get recent failed: {e}")
            return {"success": False, "error": str(e), "results": []}
    
    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话摘要信息
        """
        try:
            session = self.db.query(self.AgentSession).filter(
                self.AgentSession.session_id == session_id
            ).first()
            
            if not session:
                return {"success": False, "error": "Session not found"}
            
            # 获取消息统计
            user_count = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.session_id == session.id,
                self.AgentMessage.role == "user"
            ).count()
            
            assistant_count = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.session_id == session.id,
                self.AgentMessage.role == "assistant"
            ).count()
            
            # 获取第一条和最后一条消息
            first_msg = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.session_id == session.id
            ).order_by(self.AgentMessage.created_at.asc()).first()
            
            last_msg = self.db.query(self.AgentMessage).filter(
                self.AgentMessage.session_id == session.id
            ).order_by(self.AgentMessage.created_at.desc()).first()
            
            return {
                "success": True,
                "session_id": session_id,
                "title": session.title,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
                "message_count": session.message_count or 0,
                "user_message_count": user_count,
                "assistant_message_count": assistant_count,
                "first_message": first_msg.content[:200] if first_msg else None,
                "last_message": last_msg.content[:200] if last_msg else None,
                "total_tokens": session.total_tokens or 0
            }
            
        except Exception as e:
            logger.error(f"Get session summary failed: {e}")
            return {"success": False, "error": str(e)}
    
    def close(self):
        """关闭连接"""
        if self._db:
            self._db.close()
            self._db = None
