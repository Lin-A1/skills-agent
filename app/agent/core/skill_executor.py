"""
Skill Executor - 动态加载和执行 Skills

完全从 services/*/SKILL.md 自动发现技能，无需硬编码配置
"""
import importlib
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SkillExecutor:
    """
    技能执行器
    
    - 自动发现 services/*/SKILL.md 中定义的技能
    - 从 SKILL.md frontmatter 读取：
      - name: 技能名称
      - description: 技能描述
      - client_class: 客户端类名
      - default_method: 默认调用方法
    - 动态加载各服务的 client.py
    - 执行技能方法并返回结果
    """
    
    def __init__(self):
        # 使用 SkillRegistry 自动发现技能
        try:
            from services.skill import SkillRegistry
            self.registry = SkillRegistry()
            logger.info(f"Loaded {len(self.registry)} skills from SkillRegistry")
        except Exception as e:
            logger.warning(f"Failed to load SkillRegistry: {e}")
            self.registry = None
        
        # 客户端缓存（懒加载）
        self._clients: Dict[str, Any] = {}
    
    def _get_skill_meta(self, skill_name: str) -> Dict[str, Any]:
        """从 SKILL.md 获取技能元数据"""
        if self.registry:
            skill = self.registry.get(skill_name)
            if skill:
                return skill.get("metadata", {})
        return {}
    
    def _get_client(self, skill_name: str) -> Any:
        """
        获取或创建服务客户端实例（从 SKILL.md 读取类名）
        
        Args:
            skill_name: 技能/服务名称
            
        Returns:
            客户端实例
        """
        if skill_name in self._clients:
            return self._clients[skill_name]
        
        try:
            # 从 SKILL.md 获取客户端类名
            meta = self._get_skill_meta(skill_name)
            class_name = meta.get("client_class")
            
            if not class_name:
                # 降级：尝试通用命名模式
                # skill_name: xxx_service -> XxxClient 或 XxxServiceClient
                parts = skill_name.replace("_service", "").split("_")
                class_name = "".join(p.capitalize() for p in parts) + "Client"
                logger.warning(f"No client_class in SKILL.md for {skill_name}, guessing: {class_name}")
            
            # 动态导入 client 模块
            module_path = f"services.{skill_name}.client"
            module = importlib.import_module(module_path)
            
            # 获取客户端类
            client_class = getattr(module, class_name)
            client = client_class()
            
            self._clients[skill_name] = client
            logger.info(f"Loaded client for skill: {skill_name} (class: {class_name})")
            return client
            
        except Exception as e:
            logger.error(f"Failed to load client for {skill_name}: {e}")
            raise ValueError(f"无法加载技能 {skill_name}: {e}")
    
    def _get_default_method(self, skill_name: str) -> str:
        """从 SKILL.md 获取默认方法名"""
        meta = self._get_skill_meta(skill_name)
        return meta.get("default_method", "execute")
    
    async def execute(
        self,
        skill_name: str,
        method: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行技能方法
        
        Args:
            skill_name: 技能名称
            method: 方法名称（可选，默认使用 SKILL.md 中定义的 default_method）
            arguments: 方法参数
            
        Returns:
            包含执行结果的字典
        """
        start_time = time.time()
        arguments = arguments or {}
        
        # 确定要调用的方法（从 SKILL.md 读取默认方法）
        if not method or method == "execute":
            method = self._get_default_method(skill_name)
        
        try:
            # 获取客户端
            client = self._get_client(skill_name)
            
            # 获取方法
            if not hasattr(client, method):
                raise ValueError(f"技能 {skill_name} 没有方法 {method}")
            
            func = getattr(client, method)
            
            # 执行方法（支持同步和异步）
            import asyncio
            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                # 同步方法，在线程池中执行避免阻塞
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: func(**arguments))
            
            execution_time = time.time() - start_time
            
            return {
                "success": True,
                "result": result,
                "error": None,
                "execution_time": execution_time
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Skill execution failed: {skill_name}.{method} - {e}")
            
            return {
                "success": False,
                "result": None,
                "error": str(e),
                "execution_time": execution_time
            }
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        获取所有可用工具的列表（完全从 SKILL.md 读取）
        
        Returns:
            工具信息列表
        """
        if self.registry:
            # 从 SkillRegistry 获取技能列表
            skills = self.registry.list_all()
            result = []
            for skill in skills:
                name = skill["name"]
                meta = self._get_skill_meta(name)
                result.append({
                    "name": name,
                    "description": skill["description"],
                    "client_class": meta.get("client_class", ""),
                    "default_method": meta.get("default_method", "execute"),
                    "methods": self._get_skill_methods(name)
                })
            return result
        else:
            return []
    
    def _get_skill_methods(self, skill_name: str) -> List[str]:
        """获取技能支持的方法列表"""
        default_method = self._get_default_method(skill_name)
        
        # 尝试从已加载的客户端获取公开方法
        if skill_name in self._clients:
            client = self._clients[skill_name]
            methods = [
                m for m in dir(client)
                if not m.startswith("_") and callable(getattr(client, m))
            ]
            return methods
        
        return [default_method, "health_check"]
    
    def match_tools(self, query: str, top_n: int = 3) -> List[str]:
        """
        根据用户查询匹配相关技能
        
        Args:
            query: 用户查询
            top_n: 返回数量
            
        Returns:
            匹配的技能名称列表
        """
        if self.registry:
            return self.registry.match(query, top_n=top_n)
        return []
    
    def get_skills_prompt(self, skill_names: Optional[List[str]] = None) -> str:
        """
        获取技能的 Prompt 描述（供 LLM 使用）
        
        Args:
            skill_names: 指定的技能列表，为空则返回所有技能
            
        Returns:
            Prompt 文本
        """
        if not self.registry:
            return ""
        
        if skill_names:
            return self.registry.get_prompt(skill_names)
        else:
            return self.registry.get_all_prompt()
    
    def close(self):
        """清理资源"""
        self._clients.clear()
        logger.info("SkillExecutor closed")


# 全局技能执行器实例
skill_executor = SkillExecutor()
