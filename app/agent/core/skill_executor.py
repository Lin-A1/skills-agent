"""
Skill Executor - 动态加载和执行 Skills

完全从 services/*/SKILL.md 自动发现技能，无需硬编码配置。

重构说明：
- 将原 SkillRegistry 的功能内联到 SkillExecutor
- 消除 services/skill.py 的重复代码
- 保持 API 兼容性
"""
import importlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class SkillExecutor:
    """
    技能执行器
    
    功能：
    - 自动发现 services/*/SKILL.md 中定义的技能
    - 从 SKILL.md frontmatter 读取元数据
    - 动态加载服务客户端
    - 执行技能方法
    - 使用 Rerank 进行语义匹配
    """
    
    # 默认相关性阈值
    DEFAULT_RELEVANCE_THRESHOLD = 0.3
    
    def __init__(
        self, 
        services_dir: Optional[Path] = None,
        relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD
    ):
        """
        初始化技能执行器
        
        Args:
            services_dir: 服务目录路径，默认为 services/
            relevance_threshold: rerank 相关性阈值
        """
        # 确定 services 目录路径
        if services_dir:
            self.services_dir = services_dir
        else:
            # 默认路径：项目根目录下的 services/
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent.parent
            self.services_dir = project_root / "services"
        
        self.relevance_threshold = relevance_threshold
        
        # 技能缓存
        self._skills: Dict[str, dict] = {}
        # 客户端缓存（懒加载）
        self._clients: Dict[str, Any] = {}
        # Rerank 客户端（懒加载）
        self._rerank_client = None
        
        # 扫描技能
        self._scan_skills()
        logger.info(f"Loaded {len(self._skills)} skills from {self.services_dir}")
    
    # ============== 技能发现 ==============
    
    def _scan_skills(self) -> None:
        """扫描所有服务目录，加载 SKILL.md"""
        if not self.services_dir.exists():
            logger.warning(f"Services directory not found: {self.services_dir}")
            return
        
        for item in self.services_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith(("_", ".")):
                continue

            skill_file = item / "SKILL.md"
            if skill_file.exists():
                try:
                    self._skills[item.name] = self._parse_skill(skill_file)
                except Exception as e:
                    logger.warning(f"Failed to parse {skill_file}: {e}")
    
    def _parse_skill(self, path: Path) -> dict:
        """解析 SKILL.md 的 frontmatter 和内容"""
        content = path.read_text(encoding="utf-8")
        
        # 解析 YAML frontmatter
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
        if match:
            metadata = yaml.safe_load(match.group(1)) or {}
            body = match.group(2).strip()
            return {"metadata": metadata, "body": body, "path": str(path)}
        
        return {"metadata": {}, "body": content.strip(), "path": str(path)}
    
    def _get_skill_meta(self, skill_name: str) -> Dict[str, Any]:
        """获取技能元数据"""
        skill = self._skills.get(skill_name)
        if skill:
            return skill.get("metadata", {})
        return {}
    
    # ============== Rerank 匹配 ==============
    
    @property
    def rerank_client(self):
        """懒加载 rerank 客户端"""
        if self._rerank_client is None:
            try:
                from services.rerank_service.client import RerankServiceClient
                self._rerank_client = RerankServiceClient()
            except Exception as e:
                logger.warning(f"Failed to load RerankServiceClient: {e}")
        return self._rerank_client
    
    def _build_skill_doc(self, skill: dict) -> str:
        """构建用于 rerank 的 skill 描述文档"""
        meta = skill["metadata"]
        name = meta.get("name", "unknown")
        desc = meta.get("description", "")
        return f"{name}: {desc}"
    
    def match_tools(
        self, 
        query: str, 
        top_n: int = 3,
        threshold: Optional[float] = None
    ) -> List[str]:
        """
        根据用户查询匹配相关技能
        
        使用 Rerank 服务进行语义匹配
        """
        if not self._skills:
            return []

        threshold = threshold if threshold is not None else self.relevance_threshold
        
        skill_names = list(self._skills.keys())
        documents = [self._build_skill_doc(self._skills[name]) for name in skill_names]

        try:
            if not self.rerank_client:
                return []
            
            result = self.rerank_client.rerank(
                query=query,
                documents=documents,
                top_n=top_n,
                return_documents=False,
            )

            matched = []
            for item in result.get("results", []):
                if item["relevance_score"] >= threshold:
                    matched.append(skill_names[item["index"]])

            return matched

        except Exception as e:
            logger.warning(f"Rerank failed: {e}")
            return []
    
    # ============== 执行能力检查 ==============
    
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
    
    # ============== 客户端管理 ==============
    
    def _get_client(self, skill_name: str) -> Optional[Any]:
        """
        获取或创建服务客户端实例（从 SKILL.md 读取类名）
        """
        if not self._is_executable(skill_name):
            logger.debug(f"Skill {skill_name} is not executable (documentation only)")
            return None
        
        if skill_name in self._clients:
            return self._clients[skill_name]
        
        try:
            meta = self._get_skill_meta(skill_name)
            class_name = meta.get("client_class")
            
            if not class_name:
                # 降级：尝试通用命名模式
                parts = skill_name.replace("_service", "").split("_")
                class_name = "".join(p.capitalize() for p in parts) + "Client"
                logger.warning(f"No client_class in SKILL.md for {skill_name}, guessing: {class_name}")
            
            # 动态导入 client 模块
            module_path = f"services.{skill_name}.client"
            module = importlib.import_module(module_path)
            
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
    
    # ============== 执行方法 ==============
    
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
        
        # 确定要调用的方法
        if not method or method == "execute":
            method = self._get_default_method(skill_name)
        
        try:
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
    
    # ============== 查询方法 ==============
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取所有可用工具的列表"""
        # 第一遍：收集所有技能信息和关联关系
        all_tools = {}
        related_docs = {}  # tool_name -> [related doc content]
        
        for dir_name, skill in self._skills.items():
            meta = skill.get("metadata", {})
            name = meta.get("name", dir_name)
            is_executable = self._is_executable(dir_name)
            
            tool_info = {
                "name": name,
                "dir_name": dir_name,
                "description": meta.get("description", ""),
                "client_class": meta.get("client_class", ""),
                "default_method": meta.get("default_method", "execute"),
                "methods": self._get_skill_methods(dir_name) if is_executable else [],
                "executable": is_executable
            }
            
            # 对于文档类技能，包含完整的 body 内容
            if not is_executable and skill.get("body"):
                tool_info["body"] = skill["body"]
                    
                # 处理关联关系
                related_tools = meta.get("related_tools", [])
                for related_tool in related_tools:
                    if related_tool not in related_docs:
                        related_docs[related_tool] = []
                    related_docs[related_tool].append({
                        "name": name,
                        "body": skill["body"]
                    })
            
            all_tools[name] = tool_info
        
        # 第二遍：将关联文档附加到可执行工具
        result = []
        for name, tool_info in all_tools.items():
            if tool_info["executable"] and name in related_docs:
                tool_info["related_docs"] = related_docs[name]
            result.append(tool_info)
        
        return result
    
    def _get_skill_methods(self, skill_name: str) -> List[str]:
        """获取技能支持的方法列表"""
        default_method = self._get_default_method(skill_name)
        
        if skill_name in self._clients:
            client = self._clients[skill_name]
            methods = [
                m for m in dir(client)
                if not m.startswith("_") and callable(getattr(client, m))
            ]
            return methods
        
        return [default_method, "health_check"]
    
    def get_skills_prompt(self, skill_names: Optional[List[str]] = None) -> str:
        """获取技能的 Prompt 描述（供 LLM 使用）"""
        if skill_names is None:
            skill_names = list(self._skills.keys())
        
        parts = []
        for dir_name in skill_names:
            skill = self._skills.get(dir_name)
            if skill:
                name = skill["metadata"].get("name", dir_name)
                parts.append(f"# {name}\n\n{skill['body']}")

        return "\n\n---\n\n".join(parts)
    
    def list_all(self) -> List[dict]:
        """列出所有可用 skills 的摘要"""
        return [
            {
                "name": skill["metadata"].get("name", dir_name),
                "dir_name": dir_name,
                "description": skill["metadata"].get("description", ""),
            }
            for dir_name, skill in self._skills.items()
        ]
    
    def get(self, name: str) -> Optional[dict]:
        """获取指定 skill 的完整信息"""
        return self._skills.get(name)
    
    def __len__(self) -> int:
        return len(self._skills)
    
    def close(self):
        """清理资源"""
        self._clients.clear()
        logger.info("SkillExecutor closed")


# 全局技能执行器实例
skill_executor = SkillExecutor()
