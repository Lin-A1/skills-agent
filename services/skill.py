"""
Skill 注册表 - 发现、匹配、加载 Agent Skills

用法:
    from services.skill_registry import SkillRegistry
    
    registry = SkillRegistry()
    
    # 列出所有可用 skills
    skills = registry.list_all()
    
    # 根据用户意图匹配 skills（使用 rerank AI 匹配）
    matched = registry.match("帮我分析文档的语义相似度")
    
    # 获取 prompt 片段
    prompt = registry.get_prompt(matched)
"""

import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from services.rerank_service.client import RerankServiceClient


class SkillRegistry:
    """Skill 注册表 - 发现、匹配、加载 skills"""

    # 默认相关性阈值
    DEFAULT_RELEVANCE_THRESHOLD = 0.3

    def __init__(
            self,
            services_dir: Optional[Path] = None,
            relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    ):
        """
        初始化注册表
        
        Args:
            services_dir: 服务目录路径，默认为当前文件所在目录
            relevance_threshold: rerank 相关性阈值，低于此值不匹配
        """
        self.services_dir = services_dir or Path(__file__).parent
        self.relevance_threshold = relevance_threshold
        self.skills: dict[str, dict] = {}
        self._rerank_client: Optional["RerankServiceClient"] = None
        self._scan_skills()

    @property
    def rerank_client(self) -> "RerankServiceClient":
        """懒加载 rerank 客户端"""
        if self._rerank_client is None:
            # 动态导入以避免循环依赖和路径问题
            from rerank_service.client import RerankServiceClient
            self._rerank_client = RerankServiceClient()
        return self._rerank_client

    def _scan_skills(self) -> None:
        """扫描所有服务目录，加载 skill.md"""
        for item in self.services_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith(("_", ".")):
                continue

            skill_file = item / "SKILL.md"
            if skill_file.exists():
                try:
                    self.skills[item.name] = self._parse_skill(skill_file)
                except Exception as e:
                    print(f"Warning: Failed to parse {skill_file}: {e}")

    def _parse_skill(self, path: Path) -> dict:
        """
        解析 skill.md 的 frontmatter 和内容
        
        Args:
            path: skill.md 文件路径
            
        Returns:
            包含 metadata, body, path 的字典
        """
        content = path.read_text(encoding="utf-8")

        # 解析 YAML frontmatter
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
        if match:
            metadata = yaml.safe_load(match.group(1)) or {}
            body = match.group(2).strip()
            return {"metadata": metadata, "body": body, "path": str(path)}

        return {"metadata": {}, "body": content.strip(), "path": str(path)}

    def _build_skill_doc(self, skill: dict) -> str:
        """构建用于 rerank 的 skill 描述文档"""
        meta = skill["metadata"]
        name = meta.get("name", "unknown")
        desc = meta.get("description", "")
        return f"{name}: {desc}"

    def match(
            self,
            query: str,
            top_n: int = 3,
            threshold: Optional[float] = None,
    ) -> list[str]:
        """
        使用 rerank 服务进行语义匹配
        
        Args:
            query: 用户查询/意图
            top_n: 最多返回的 skill 数量
            threshold: 相关性阈值，默认使用实例阈值
            
        Returns:
            匹配的 skill 名称列表（按相关性降序）
        """
        if not self.skills:
            return []

        threshold = threshold if threshold is not None else self.relevance_threshold

        # 构建 skill 名称和描述的映射
        skill_names = list(self.skills.keys())
        documents = [self._build_skill_doc(self.skills[name]) for name in skill_names]

        try:
            # 使用 rerank 服务评分
            result = self.rerank_client.rerank(
                query=query,
                documents=documents,
                top_n=top_n,
                return_documents=False,
            )

            # 筛选超过阈值的结果
            matched = []
            for item in result.get("results", []):
                if item["relevance_score"] >= threshold:
                    matched.append(skill_names[item["index"]])

            return matched

        except Exception as e:
            print(f"Warning: Rerank failed: {e}")
            return []

    def get_prompt(self, skill_names: list[str]) -> str:
        """
        生成供 LLM 使用的 prompt 片段
        
        Args:
            skill_names: 要加载的 skill 名称列表
            
        Returns:
            组合后的 prompt 文本
        """
        parts = []
        for name in skill_names:
            if name in self.skills:
                skill = self.skills[name]
                skill_name = skill["metadata"].get("name", name)
                parts.append(f"# {skill_name}\n\n{skill['body']}")

        return "\n\n---\n\n".join(parts)

    def get_all_prompt(self) -> str:
        """
        获取所有 skills 的 prompt
        
        Returns:
            所有 skills 组合的 prompt 文本
        """
        return self.get_prompt(list(self.skills.keys()))

    def list_all(self) -> list[dict]:
        """
        列出所有可用 skills 的摘要
        
        Returns:
            skill 摘要列表
        """
        return [
            {
                "name": skill["metadata"].get("name", name),
                "dir_name": name,  # 目录名，用于 registry.get()
                "description": skill["metadata"].get("description", ""),
            }
            for name, skill in self.skills.items()
        ]

    def get(self, name: str) -> Optional[dict]:
        """
        获取指定 skill 的完整信息
        
        Args:
            name: skill 名称
            
        Returns:
            skill 信息字典，不存在则返回 None
        """
        return self.skills.get(name)

    def __len__(self) -> int:
        return len(self.skills)

    def __repr__(self) -> str:
        return f"SkillRegistry(skills={list(self.skills.keys())})"


if __name__ == "__main__":
    # 测试代码
    registry = SkillRegistry()

    # 列出所有可用 skills
    skills = registry.list_all()

    # 根据用户意图匹配 skills（使用 rerank AI 匹配）
    matched = registry.match("向量化")

    # 获取 prompt 片段
    prompt = registry.get_prompt(matched)

    print('')