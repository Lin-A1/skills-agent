import os
from typing import List, Optional

class FileServiceClient:
    """文件服务客户端，用于操作共享工作区文件"""
    
    def __init__(self, session_id: Optional[str] = None):
        """
        初始化文件服务客户端
        Args:
            session_id: 默认会话ID。如果提供，所有操作默认在此会话目录下进行。
        """
        # 基础工作区路径 (宿主机挂载点)
        self.base_workspace = os.getenv("WORKSPACE_PATH", "/workspace")
        self.session_id = session_id
        
        # 确保基础路径存在
        if not os.path.exists(self.base_workspace):
            try:
                os.makedirs(self.base_workspace, exist_ok=True)
                os.chmod(self.base_workspace, 0o777)
            except OSError:
                pass

    def _get_full_path(self, path: str, session_id: Optional[str] = None) -> str:
        """
        获取完整路径
        
        Args:
            path: 用户路径
            session_id: 会话ID，如果未提供则使用实例默认值
        """
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("Session ID is required for file operations")
            
        # 构造会话特定的工作区路径
        session_workspace = os.path.join(self.base_workspace, sid)
        
        # 确保会话目录存在并有写入权限
        if not os.path.exists(session_workspace):
            try:
                os.makedirs(session_workspace, exist_ok=True)
                os.chmod(session_workspace, 0o777)
            except OSError:
                pass
        
        # 移除开头的 /
        clean_path = path.lstrip("/")
        full_path = os.path.join(session_workspace, clean_path)
        
        # 安全检查
        if not os.path.abspath(full_path).startswith(os.path.abspath(session_workspace)):
            raise ValueError(f"Access denied: {path} is outside session workspace")
            
        return full_path

    def list_files(self, sub_dir: str = "", session_id: Optional[str] = None) -> List[str]:
        """列出会话工作区文件"""
        try:
            target_dir = self._get_full_path(sub_dir, session_id)
        except ValueError:
            return []
            
        if not os.path.exists(target_dir):
            return []
            
        results = []
        # 计算相对路径的基准目录
        sid = session_id or self.session_id
        base_dir = os.path.join(self.base_workspace, sid)
        
        for root, _, files in os.walk(target_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, base_dir)
                results.append(rel_path)
        return sorted(results)

    def read_file(self, path: str, session_id: Optional[str] = None) -> str:
        """读取文件内容"""
        full_path = self._get_full_path(path, session_id)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {path}")
            
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path: str, content: str, session_id: Optional[str] = None) -> str:
        """写入文件内容"""
        full_path = self._get_full_path(path, session_id)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"Successfully wrote to {path}"

    def delete_file(self, path: str, session_id: Optional[str] = None) -> str:
        """删除文件"""
        full_path = self._get_full_path(path, session_id)
        if os.path.exists(full_path):
            os.remove(full_path)
            return f"Successfully deleted {path}"
        return f"File not found: {path}"
