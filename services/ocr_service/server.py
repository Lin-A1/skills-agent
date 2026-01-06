import base64
import io
import logging
import os
from typing import List

import numpy as np
import uvicorn
import paddle
from PIL import Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from paddleocr import PaddleOCR

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ===== Pydantic 模型 =====
class OCRRequest(BaseModel):
    """OCR 请求模型"""
    image: str = Field(..., description="Base64 编码的图片数据")


class OCRResponse(BaseModel):
    """OCR 响应模型"""
    result: List


# ===== OCR 分析器 =====
class OCRService:
    """统一的 OCR 服务封装"""

    def __init__(self):
        logger.info("初始化 PaddleOCR 引擎")

        self.ocr = PaddleOCR(
            use_angle_cls=True,       # 启用文本方向分类
            lang="ch",                # 中文识别
        )

    @staticmethod
    def base64_to_image(base64_str: str, max_size: int = 2048) -> np.ndarray:
        """Base64 转 numpy 图像，并限制最大尺寸以降低显存占用"""
        try:
            if base64_str.startswith("data:image"):
                base64_str = base64_str.split(",", 1)[1]

            image_bytes = base64.b64decode(base64_str)
            pil_image = Image.open(io.BytesIO(image_bytes))

            if pil_image.mode == "RGBA":
                pil_image = pil_image.convert("RGB")

            # 限制图片最大尺寸，避免大图片导致显存暴涨
            width, height = pil_image.size
            if max(width, height) > max_size:
                scale = max_size / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"图片缩放: {width}x{height} -> {new_width}x{new_height}")

            return np.array(pil_image)

        except Exception as e:
            logger.error(f"Base64 转图片失败: {e}")
            raise ValueError("无效的 Base64 图片数据")

    def recognize(self, base64_image: str) -> List:
        """执行 OCR 识别"""
        image = self.base64_to_image(base64_image)
        
        try:
            result = self.ocr.predict(image)
            # 保持原始返回结构
            return [res.json["res"] for res in result]
        finally:
            # 每次推理后清理 GPU 显存缓存
            if paddle.device.is_compiled_with_cuda():
                paddle.device.cuda.empty_cache()


# ===== FastAPI 应用 =====
app = FastAPI(
    title="OCR 服务 API",
    description="基于 PaddleOCR 的中文 OCR 识别服务",
    version="1.0.0",
)

# 全局 OCR 服务实例
ocr_service: OCRService | None = None


@app.on_event("startup")
async def startup_event():
    """服务启动初始化"""
    global ocr_service
    try:
        ocr_service = OCRService()
        logger.info("OCR 服务启动成功")
    except Exception as e:
        logger.error(f"OCR 服务初始化失败: {e}")
        raise


@app.get("/health")
async def health_check() -> dict:
    """健康检查接口"""
    return {"status": "healthy"}


@app.post("/ocr", response_model=OCRResponse)
async def ocr_recognize(request: OCRRequest):
    """OCR 识别接口（API / 输入 / 输出保持不变）"""
    if not ocr_service:
        raise HTTPException(status_code=503, detail="OCR 服务未初始化")

    try:
        result = ocr_service.recognize(request.image)
        return {"result": result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("OCR 处理失败")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 启动入口 =====
if __name__ == "__main__":

    def _get_port_from_env() -> int:
        """读取 OCR 服务端口"""
        val = os.getenv("OCR_PORT", "8001")
        try:
            return int(val)
        except ValueError:
            return 8001

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=_get_port_from_env(),
        reload=False,
        log_level="info",
    )
