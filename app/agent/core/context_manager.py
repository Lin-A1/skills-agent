"""
Context Manager - Handles persistent memory and context management

核心职责：
1. 管理 Agent 的持久化记忆（facts, preferences, context）
2. 构建发送给 LLM 的上下文消息
3. 管理系统提示词（包含日期信息和 Skills 列表）
4. 处理消息历史的截断和优化
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import json

from sqlalchemy.orm import Session as DBSession

from ..config import settings
from .skill_registry import get_skill_registry

logger = logging.getLogger(__name__)


# 默认系统提示词模板
DEFAULT_SYSTEM_PROMPT = """你是一个智能AI助手，具备调用各种技能（Skills）来完成复杂任务的能力。

## 当前时间
今天是 {date}（{weekday}），当前时间 {time}（UTC）。

## 可用技能
你可以通过阅读技能文档来了解如何使用它们。当用户的请求需要某个技能时，你应该：
1. 阅读相关技能的 SKILL.md 文档
2. 根据文档中的调用方式编写代码
3. 使用 <execute_skill> 工具执行代码
4. 分析执行结果并给出回答

{available_skills}

## 执行技能
当你需要执行技能代码时，使用以下格式：

```xml
<execute_skill>
<skill_name>技能名称</skill_name>
<code>
# Python 代码
# 参考 SKILL.md 中的调用方式
</code>
</execute_skill>
```

## 重要规则
1. 你可以在一次回答中多次调用技能，直到获得满意的结果
2. 每次执行后分析结果，决定是否需要继续调用
3. 如果执行失败，分析错误并尝试修正代码
4. 技能调用应该经过信任模式（trusted_mode=True），这样可以访问其他服务
5. 保持对话的连贯性，记住上下文信息

## 记忆与上下文
{memory_context}

请用中文回答，除非用户明确要求其他语言。
"""


@dataclass
class MemoryItem:
    """记忆项"""
    key: str
    value: Any
    memory_type: str  # fact, preference, context
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "memory_type": self.memory_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }


class ContextManager:
    """
    上下文管理器
    
    管理 Agent 的记忆、系统提示词和消息上下文。
    """
    
    def __init__(self):
        """初始化上下文管理器"""
        self._session_memories: Dict[str, Dict[str, MemoryItem]] = {}
        self._global_memories: Dict[str, MemoryItem] = {}
        self._skill_registry = get_skill_registry()
        
        logger.info("ContextManager initialized")
    
    # ==================== Memory Management ====================
    
    def set_memory(
        self,
        session_id: str,
        key: str,
        value: Any,
        memory_type: str = "fact",
        ttl: Optional[int] = None
    ) -> MemoryItem:
        """
        设置会话记忆
        
        Args:
            session_id: 会话ID
            key: 记忆键名
            value: 记忆值
            memory_type: 类型 (fact, preference, context)
            ttl: 过期时间（秒）
            
        Returns:
            MemoryItem 对象
        """
        if session_id not in self._session_memories:
            self._session_memories[session_id] = {}
        
        expires_at = None
        if ttl is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        
        now = datetime.now(timezone.utc)
        
        # 更新或创建
        if key in self._session_memories[session_id]:
            memory = self._session_memories[session_id][key]
            memory.value = value
            memory.memory_type = memory_type
            memory.updated_at = now
            memory.expires_at = expires_at
        else:
            memory = MemoryItem(
                key=key,
                value=value,
                memory_type=memory_type,
                created_at=now,
                updated_at=now,
                expires_at=expires_at
            )
            self._session_memories[session_id][key] = memory
        
        logger.debug(f"Set memory [{session_id}] {key} = {value}")
        return memory
    
    def get_memory(self, session_id: str, key: str) -> Optional[Any]:
        """获取会话记忆"""
        if session_id not in self._session_memories:
            return None
        
        memory = self._session_memories[session_id].get(key)
        if memory is None:
            return None
        
        if memory.is_expired():
            del self._session_memories[session_id][key]
            return None
        
        return memory.value
    
    def get_all_memories(self, session_id: str) -> Dict[str, MemoryItem]:
        """获取会话的所有记忆"""
        if session_id not in self._session_memories:
            return {}
        
        # 清理过期记忆
        memories = self._session_memories[session_id]
        expired_keys = [k for k, v in memories.items() if v.is_expired()]
        for key in expired_keys:
            del memories[key]
        
        return memories
    
    def delete_memory(self, session_id: str, key: str) -> bool:
        """删除会话记忆"""
        if session_id not in self._session_memories:
            return False
        if key not in self._session_memories[session_id]:
            return False
        
        del self._session_memories[session_id][key]
        return True
    
    def clear_session_memories(self, session_id: str) -> None:
        """清空会话的所有记忆"""
        if session_id in self._session_memories:
            del self._session_memories[session_id]
    
    def set_global_memory(
        self,
        key: str,
        value: Any,
        memory_type: str = "fact"
    ) -> MemoryItem:
        """设置全局记忆（跨会话）"""
        now = datetime.now(timezone.utc)
        
        if key in self._global_memories:
            memory = self._global_memories[key]
            memory.value = value
            memory.memory_type = memory_type
            memory.updated_at = now
        else:
            memory = MemoryItem(
                key=key,
                value=value,
                memory_type=memory_type,
                created_at=now,
                updated_at=now
            )
            self._global_memories[key] = memory
        
        return memory
    
    def get_global_memory(self, key: str) -> Optional[Any]:
        """获取全局记忆"""
        memory = self._global_memories.get(key)
        return memory.value if memory else None
    
    # ==================== System Prompt ====================
    
    def build_system_prompt(
        self,
        session_id: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        include_skills: bool = True,
        include_memory: bool = True
    ) -> str:
        """
        构建系统提示词
        
        Args:
            session_id: 会话ID（用于获取会话记忆）
            custom_prompt: 自定义提示词（如果提供，将使用此模板）
            include_skills: 是否包含 Skills 列表
            include_memory: 是否包含记忆上下文
            
        Returns:
            完整的系统提示词
        """
        # 获取日期信息
        date_info = settings.get_current_date_info()
        
        # 获取 Skills 摘要
        skills_summary = ""
        if include_skills:
            skills_summary = self._skill_registry.get_skills_summary()
        
        # 构建记忆上下文
        memory_context = ""
        if include_memory and session_id:
            memories = self.get_all_memories(session_id)
            if memories:
                memory_lines = ["以下是关于这次对话的已知信息："]
                for key, item in memories.items():
                    value_str = json.dumps(item.value, ensure_ascii=False) if isinstance(item.value, (dict, list)) else str(item.value)
                    memory_lines.append(f"- {key}: {value_str}")
                memory_context = "\n".join(memory_lines)
            else:
                memory_context = "暂无已知信息。"
        else:
            memory_context = "暂无已知信息。"
        
        # 使用自定义模板或默认模板
        template = custom_prompt or DEFAULT_SYSTEM_PROMPT
        
        # 填充模板
        system_prompt = template.format(
            date=date_info["date"],
            weekday=date_info["weekday"],
            time=date_info["time"],
            timestamp=date_info["timestamp"],
            year=date_info["year"],
            month=date_info["month"],
            day=date_info["day"],
            available_skills=skills_summary,
            memory_context=memory_context
        )
        
        return system_prompt
    
    # ==================== Context Building ====================
    
    def build_context_messages(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_messages: Optional[int] = None,
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        构建发送给 LLM 的上下文消息
        
        Args:
            messages: 原始消息列表
            system_prompt: 系统提示词
            max_messages: 最大消息数量
            max_tokens: 最大 token 数量（简单估算）
            
        Returns:
            处理后的消息列表
        """
        max_messages = max_messages or settings.MAX_CONTEXT_MESSAGES
        max_tokens = max_tokens or settings.MAX_CONTEXT_TOKENS
        
        # 添加系统消息
        context = [{"role": "system", "content": system_prompt}]
        
        # 限制消息数量
        recent_messages = messages[-(max_messages - 1):] if len(messages) > max_messages - 1 else messages
        
        # 简单的 token 估算和截断
        total_tokens = self._estimate_tokens(system_prompt)
        filtered_messages = []
        
        for msg in recent_messages:
            msg_tokens = self._estimate_tokens(msg.get("content", ""))
            if total_tokens + msg_tokens <= max_tokens:
                filtered_messages.append(msg)
                total_tokens += msg_tokens
            else:
                # 超出 token 限制，截断
                break
        
        context.extend(filtered_messages)
        
        logger.debug(f"Built context with {len(context)} messages, ~{total_tokens} tokens")
        return context
    
    def _estimate_tokens(self, text: str) -> int:
        """简单估算 token 数量"""
        # 中文约 1.5 字符/token，英文约 4 字符/token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)
    
    # ==================== Skill Context ====================
    
    def get_skill_context(self, skill_names: List[str]) -> str:
        """
        获取指定 Skills 的详细内容（用于注入执行上下文）
        
        Args:
            skill_names: Skill 名称列表
            
        Returns:
            Skills 内容的合并文本
        """
        contents = []
        for name in skill_names:
            content = self._skill_registry.get_skill_content(name)
            if content:
                contents.append(f"# Skill: {name}\n\n{content}")
        
        return "\n\n---\n\n".join(contents)


# 全局上下文管理器实例
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """获取全局上下文管理器实例（单例）"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
