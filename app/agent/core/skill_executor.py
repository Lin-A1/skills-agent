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
    
    def _is_executable(self, skill_name: str) -> bool:
        """
        检查技能是否可执行
        
        可执行条件（满足任一）：
        1. SKILL.md 中 executable 字段不为 false
        2. 存在 client.py 文件
        """
        meta = self._get_skill_meta(skill_name)
        
        # 显式标记为不可执行
        if meta.get("executable") is False:
            return False
        
        # 检查是否有 client_class 或能找到 client 模块
        if meta.get("client_class"):
            return True
        
        # 尝试检测 client 模块是否存在
        try:
            import importlib.util
            spec = importlib.util.find_spec(f"services.{skill_name}.client")
            return spec is not None
        except (ModuleNotFoundError, ValueError):
            return False
    
    def _get_client(self, skill_name: str) -> Optional[Any]:
        """
        获取或创建服务客户端实例（从 SKILL.md 读取类名）
        
        Args:
            skill_name: 技能/服务名称
            
        Returns:
            客户端实例，如果技能不可执行则返回 None
        """
        # 检查是否可执行
        if not self._is_executable(skill_name):
            logger.debug(f"Skill {skill_name} is not executable (documentation only)")
            return None
        
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
            
            # 处理不可执行的技能
            if client is None:
                meta = self._get_skill_meta(skill_name)
                skill_desc = meta.get("description", "此技能仅供参考")
                return {
                    "success": False,
                    "result": None,
                    "error": f"技能 '{skill_name}' 是文档类技能，不可直接执行。描述：{skill_desc}",
                    "execution_time": time.time() - start_time,
                    "executable": False
                }
            
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
            
            # 第一遍：收集所有技能信息和关联关系
            all_tools = {}
            related_docs = {}  # tool_name -> [related doc content]
            
            for skill in skills:
                name = skill["name"]  # 显示名
                dir_name = skill.get("dir_name", name)  # 目录名
                meta = self._get_skill_meta(dir_name)
                is_executable = self._is_executable(dir_name)
                skill_data = self.registry.get(dir_name)
                
                tool_info = {
                    "name": name,
                    "dir_name": dir_name,
                    "description": skill["description"],
                    "client_class": meta.get("client_class", ""),
                    "default_method": meta.get("default_method", "execute"),
                    "methods": self._get_skill_methods(dir_name) if is_executable else [],
                    "executable": is_executable
                }
                
                # 对于文档类技能，包含完整的 body 内容
                if not is_executable and skill_data and skill_data.get("body"):
                    tool_info["body"] = skill_data["body"]
                    
                    # 处理关联关系：将此文档关联到目标工具
                    related_tools = meta.get("related_tools", [])
                    for related_tool in related_tools:
                        if related_tool not in related_docs:
                            related_docs[related_tool] = []
                        related_docs[related_tool].append({
                            "name": name,
                            "body": skill_data["body"]
                        })
                
                all_tools[name] = tool_info
            
            # 第二遍：将关联文档附加到可执行工具
            result = []
            for name, tool_info in all_tools.items():
                if tool_info["executable"] and name in related_docs:
                    tool_info["related_docs"] = related_docs[name]
                result.append(tool_info)
            
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
