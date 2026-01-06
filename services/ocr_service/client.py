"""OCR服务客户端"""
import base64
import os
import requests
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
            requests.RequestException: 请求失败时抛出异常
        """
        url = f"{self.base_url}/ocr"
        response = requests.post(url, json={"image": _image_base64})
        response.raise_for_status()
        return response.json()['result'][0]

    @staticmethod
    def image_to_base64(image_path: str) -> dict:
        """从图片文件进行OCR识别

        Args:
            image_path: 图片文件路径

        Returns:
            dict: OCR识别结果

        Raises:
            FileNotFoundError: 文件不存在时抛出异常
            requests.RequestException: 请求失败时抛出异常
        """
        with open(image_path, "rb") as f:
            image_data = f.read()
        _image_base64 = base64.b64encode(image_data).decode("utf-8")
        return _image_base64

    def health_check(self) -> dict:
        """健康检查

        Returns:
            dict: 健康状态
        """
        url = f"{self.base_url}/health"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    client = OCRServiceClient()
    print(client.health_check())
    image_base64 = client.image_to_base64("/home/lin/Pictures/267421c76d4150f3faf1489d55e210e2.jpg")
    result = client.ocr(image_base64)
    print(result)
