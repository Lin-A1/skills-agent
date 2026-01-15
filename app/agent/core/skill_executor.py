"""
Skill Executor - Executes skills via Sandbox service

核心职责：
1. 接收 Agent 引擎的 skill 调用请求
2. 读取对应 SKILL.md 中的代码示例
3. 通过 Sandbox 服务（trusted_mode）执行代码
4. 返回执行结果

关键设计：
- Agent 不直接依赖任何 Skill 的环境或代码
- 所有 Skill 调用都通过 Sandbox 隔离执行
- 支持组合多个 Skill 的代码
"""
import logging
import re
from typing import Dict, Any, Optional, List
import requests

from ..config import settings
from .skill_registry import get_skill_registry, SkillInfo

logger = logging.getLogger(__name__)


class SkillExecutor:
    """
    Skill 执行器
    
    通过 Sandbox 服务执行 Skill 中的代码。
    Agent 通过此执行器调用 Skills，保持解耦。
    """
    
    def __init__(self, sandbox_url: Optional[str] = None, timeout: float = 120.0):
        """
        初始化 Skill 执行器
        
        Args:
            sandbox_url: Sandbox 服务 URL，默认从配置读取
            timeout: 执行超时时间（秒）
        """
        self.sandbox_url = sandbox_url or settings.sandbox_service_url
        self.timeout = timeout
        self._registry = get_skill_registry()
        
        logger.info(f"SkillExecutor initialized with sandbox: {self.sandbox_url}")
    
    def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
        env_vars: Optional[Dict[str, str]] = None,
        trusted_mode: bool = True
    ) -> Dict[str, Any]:
        """
        直接执行代码（通过 Sandbox）
        
        Args:
            code: 要执行的代码
            language: 编程语言
            timeout: 超时时间（秒）
            env_vars: 环境变量
            trusted_mode: 是否使用信任模式（允许访问 services）
            
        Returns:
            执行结果 dict
        """
        url = f"{self.sandbox_url}/execute"
        payload = {
            "code": code,
            "language": language,
            "trusted_mode": trusted_mode
        }
        if timeout is not None:
            payload["timeout"] = timeout
        if env_vars is not None:
            payload["env_vars"] = env_vars
        
        try:
            response = requests.post(
                url, 
                json=payload, 
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Code execution result: success={result.get('success')}")
            return result
        except requests.exceptions.Timeout:
            logger.error(f"Sandbox execution timeout")
            return {
                "success": False,
                "stdout": "",
                "stderr": "执行超时",
                "exit_code": -1,
                "execution_time": self.timeout,
                "error": "Execution timeout"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Sandbox request failed: {e}")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": 0,
                "error": f"Request failed: {e}"
            }
    
    def execute_skill(
        self,
        skill_name: str,
        code: str,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        执行指定 Skill 的代码
        
        Args:
            skill_name: Skill 名称（用于日志和追踪）
            code: 要执行的代码（由 Agent 生成，参考 SKILL.md）
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        logger.info(f"Executing skill '{skill_name}'")
        
        # 验证 skill 存在
        skill = self._registry.get_skill(skill_name)
        if not skill:
            logger.warning(f"Skill '{skill_name}' not found, but proceeding with execution")
        
        result = self.execute_code(
            code=code,
            language="python",
            timeout=timeout or settings.ITERATION_TIMEOUT,
            trusted_mode=True  # 允许访问 services
        )
        
        # 添加 skill 信息到结果
        result["skill_name"] = skill_name
        
        return result
    
    def execute_composite_code(
        self,
        code: str,
        skill_names: List[str],
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        执行组合多个 Skill 的代码
        
        Agent 可以根据多个 SKILL.md 的内容，组合生成复合代码。
        
        Args:
            code: 组合代码
            skill_names: 涉及的 Skill 名称列表
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        logger.info(f"Executing composite code using skills: {skill_names}")
        
        result = self.execute_code(
            code=code,
            language="python",
            timeout=timeout or settings.ITERATION_TIMEOUT,
            trusted_mode=True
        )
        
        result["skill_names"] = skill_names
        result["is_composite"] = True
        
        return result
    
    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """
        获取 Skill 的完整内容
        
        Args:
            skill_name: Skill 名称
            
        Returns:
            SKILL.md 的完整内容
        """
        return self._registry.get_skill_content(skill_name)
    
    def get_skill_code_examples(self, skill_name: str) -> List[str]:
        """
        从 SKILL.md 中提取代码示例
        
        Args:
            skill_name: Skill 名称
            
        Returns:
            代码示例列表
        """
        content = self.get_skill_content(skill_name)
        if not content:
            return []
        
        # 提取 Python 代码块
        code_blocks = re.findall(
            r'```python\n(.*?)```',
            content,
            re.DOTALL
        )
        
        return code_blocks
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            url = f"{self.sandbox_url}/health"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return {
                "status": "healthy",
                "sandbox": response.json()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 全局 Skill 执行器实例
_skill_executor: Optional[SkillExecutor] = None


def get_skill_executor() -> SkillExecutor:
    """获取全局 Skill 执行器实例（单例）"""
    global _skill_executor
    if _skill_executor is None:
        _skill_executor = SkillExecutor()
    return _skill_executor
