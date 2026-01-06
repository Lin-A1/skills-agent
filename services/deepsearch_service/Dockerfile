FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 合并 RUN 层减少镜像大小
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-dotenv \
    openai \
    httpx \
    pydantic

COPY . /app/

EXPOSE ${DEEPSEARCH_SERVICE_PORT:-8007}

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${DEEPSEARCH_SERVICE_PORT:-8007}/health || exit 1

CMD ["python", "server.py"]
