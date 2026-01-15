"""
Skill Registry - Discovers and manages SKILL.md files
Following Agent Skills (https://agentskills.io) pattern

核心职责：
1. 在启动时扫描 services 目录发现 SKILL.md 文件
2. 解析 YAML frontmatter 提取 name 和 description
3. 提供 skill 列表供 Agent 系统提示词使用
4. 按需加载完整 skill 内容
"""
import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Skill 信息"""
    name: str
    description: str
    path: str
    content: Optional[str] = None
    usage_example: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "usage_example": self.usage_example
        }
    
    def to_detail_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "content": self.content or "",
            "usage_example": self.usage_example
        }


class SkillRegistry:
    """
    Skill 注册表
    
    负责发现、解析和管理 SKILL.md 文件。
    遵循 Agent Skills 规范：https://agentskills.io
    """
    
    def __init__(self, skills_directory: Optional[str] = None):
        """
        初始化 Skill 注册表
        
        Args:
            skills_directory: Skills 所在目录，默认从配置读取
        """
        self.skills_directory = skills_directory or settings.SKILLS_DIRECTORY
        self._skills: Dict[str, SkillInfo] = {}
        self._initialized = False
        
        logger.info(f"SkillRegistry initialized with directory: {self.skills_directory}")
    
    def discover_skills(self) -> None:
        """
        扫描目录发现所有 SKILL.md 文件
        """
        self._skills.clear()
        base_path = Path(self.skills_directory)
        
        if not base_path.exists():
            logger.warning(f"Skills directory does not exist: {self.skills_directory}")
            return
        
        # 递归查找所有 SKILL.md
        skill_files = list(base_path.glob("**/SKILL.md"))
        logger.info(f"Found {len(skill_files)} SKILL.md files")
        
        for skill_file in skill_files:
            try:
                skill_info = self._parse_skill_file(skill_file)
                if skill_info:
                    self._skills[skill_info.name] = skill_info
                    logger.info(f"Registered skill: {skill_info.name} from {skill_file}")
            except Exception as e:
                logger.error(f"Failed to parse skill file {skill_file}: {e}")
        
        self._initialized = True
        logger.info(f"Skill discovery complete. Total skills: {len(self._skills)}")
    
    def _parse_skill_file(self, skill_file: Path) -> Optional[SkillInfo]:
        """
        解析 SKILL.md 文件，提取 frontmatter 元数据和用法示例
        
        Args:
            skill_file: SKILL.md 文件路径
            
        Returns:
            SkillInfo 对象，解析失败返回 None
        """
        try:
            content = skill_file.read_text(encoding='utf-8')
            
            # 提取 YAML frontmatter
            frontmatter_match = re.match(
                r'^---\s*\n(.*?)\n---\s*\n',
                content,
                re.DOTALL
            )
            
            if not frontmatter_match:
                logger.warning(f"No frontmatter found in {skill_file}")
                return None
            
            frontmatter_text = frontmatter_match.group(1)
            metadata = yaml.safe_load(frontmatter_text)
            
            if not metadata:
                logger.warning(f"Empty frontmatter in {skill_file}")
                return None
            
            name = metadata.get('name')
            description = metadata.get('description')
            
            if not name or not description:
                logger.warning(f"Missing name or description in {skill_file}")
                return None
            
            # 提取用法示例 (Python代码块)
            # 查找 "## 调用方式" 或 "## Usage" 后面的 python 代码块
            usage_match = re.search(
                r'##\s*(?:调用方式|Usage).*?```python\n(.*?)\n```',
                content,
                re.DOTALL | re.IGNORECASE
            )
            
            usage_example = None
            if usage_match:
                usage_example = usage_match.group(1).strip()
            
            return SkillInfo(
                name=name,
                description=description,
                path=str(skill_file.parent),
                content=content,
                usage_example=usage_example
            )
            
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error in {skill_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing {skill_file}: {e}")
            return None
    
    def get_skill(self, name: str) -> Optional[SkillInfo]:
        """
        获取指定 Skill 的信息
        
        Args:
            name: Skill 名称
            
        Returns:
            SkillInfo 对象，不存在返回 None
        """
        if not self._initialized:
            self.discover_skills()
        return self._skills.get(name)
    
    def get_skill_content(self, name: str) -> Optional[str]:
        """
        获取指定 Skill 的完整内容（用于激活 skill 时注入上下文）
        
        Args:
            name: Skill 名称
            
        Returns:
            Skill 的完整 SKILL.md 内容
        """
        skill = self.get_skill(name)
        if skill and skill.content:
            return skill.content
        
        # 重新加载内容
        if skill:
            skill_file = Path(skill.path) / "SKILL.md"
            if skill_file.exists():
                skill.content = skill_file.read_text(encoding='utf-8')
                return skill.content
        
        return None
    
    def list_skills(self) -> List[SkillInfo]:
        """
        列出所有已注册的 Skills
        
        Returns:
            SkillInfo 列表
        """
        if not self._initialized:
            self.discover_skills()
        return list(self._skills.values())
    
    def get_skills_summary(self) -> str:
        """
        获取 Skills 摘要（用于注入系统提示词）
        
        Returns:
            XML 格式的 skills 列表，包含用法示例
        """
        if not self._initialized:
            self.discover_skills()
        
        if not self._skills:
            return "<available_skills>No skills available</available_skills>"
        
        skills_xml = ["<available_skills>"]
        for skill in self._skills.values():
            content_tag = ""
            if skill.usage_example:
                # 有代码样例，只显示样例
                content_tag = f"\n    <usage>\n```python\n{skill.usage_example}\n```\n    </usage>"
            elif skill.content:
                # 没有代码样例（指导性文档），显示完整内容（移除 frontmatter）
                # 移除 YAML frontmatter
                content_without_frontmatter = re.sub(
                    r'^---\s*\n.*?\n---\s*\n',
                    '',
                    skill.content,
                    flags=re.DOTALL
                ).strip()
                content_tag = f"\n    <full_content>\n{content_without_frontmatter}\n    </full_content>"
                
            skills_xml.append(f"""  <skill>
    <name>{skill.name}</name>
    <description>{skill.description}</description>
    <location>{skill.path}/SKILL.md</location>{content_tag}
  </skill>""")
        skills_xml.append("</available_skills>")
        
        return "\n".join(skills_xml)
    
    def get_skill_names(self) -> List[str]:
        """获取所有 Skill 名称"""
        if not self._initialized:
            self.discover_skills()
        return list(self._skills.keys())
    
    def refresh(self) -> None:
        """刷新 Skill 列表（重新扫描）"""
        self._initialized = False
        self.discover_skills()


# 全局 Skill 注册表实例
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取全局 Skill 注册表实例（单例）"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
        if settings.SKILLS_AUTO_DISCOVER:
            _skill_registry.discover_skills()
    return _skill_registry


def refresh_skill_registry() -> None:
    """刷新全局 Skill 注册表"""
    registry = get_skill_registry()
    registry.refresh()
