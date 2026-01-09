"""OCR服务客户端"""
import base64
import json
import os
import urllib.request
import urllib.error
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# 加载.env文件
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class OCRServiceClient:
    """OCR服务客户端类"""

    def __init__(self, base_url: Optional[str] = None):
        """初始化OCR服务客户端

        Args:
            base_url: OCR服务地址，默认从环境变量读取或使用localhost:8001
        """
        if base_url is None:
            host = os.getenv("OCR_HOST", "localhost")
            port = os.getenv("OCR_PORT", "8001")
            base_url = f"http://{host}:{port}"

        self.base_url = base_url.rstrip("/")

    def ocr(self, _image_base64: str) -> dict:
        """调用OCR识别接口

        Args:
            _image_base64: Base64编码的图片字符串

        Returns:
            dict: OCR识别结果

        Raises:
            urllib.error.URLError: 请求失败时抛出异常
        """
        url = f"{self.base_url}/ocr"
        data = json.dumps({"image": _image_base64}).encode("utf-8")
        
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result['result'][0]

    @staticmethod
    def image_to_base64(image_path: str) -> str:
        """从图片文件进行OCR识别

        Args:
            image_path: 图片文件路径

        Returns:
            str: Base64编码的字符串

        Raises:
            FileNotFoundError: 文件不存在时抛出异常
        """
        with open(image_path, "rb") as f:
            image_data = f.read()
        return base64.b64encode(image_data).decode("utf-8")

    def health_check(self) -> dict:
        """健康检查

        Returns:
            dict: 健康状态
        """
        url = f"{self.base_url}/health"
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    client = OCRServiceClient()
    try:
        print(client.health_check())
        # image_base64 = client.image_to_base64("path/to/image.jpg")
        # result = client.ocr(image_base64)
        # print(result)
    except Exception as e:
        print(f"Check failed: {e}")
