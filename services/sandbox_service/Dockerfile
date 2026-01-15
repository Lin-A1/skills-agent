FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 安装必要依赖和 Docker CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-dotenv \
    httpx \
    pydantic \
    requests

# 安装 Docker CLI (静态二进制)
ARG DOCKER_VERSION=24.0.7
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz \
    | tar -xz -C /usr/local/bin --strip-components=1 docker/docker

COPY . /app/

EXPOSE ${SANDBOX_SERVICE_PORT:-8010}

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${SANDBOX_SERVICE_PORT:-8010}/health || exit 1

CMD ["python", "server.py"]

