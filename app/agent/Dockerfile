# Agent App Dockerfile
# Intelligent Agent API built with FastAPI

FROM python:3.11-slim

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 配置pip国内镜像
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 安装Python依赖
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-dotenv \
    openai \
    sqlalchemy \
    psycopg2-binary \
    pydantic \
    pydantic-settings \
    httpx \
    requests \
    pyyaml

# 复制应用代码
COPY app/ /app/app/
COPY services/ /app/services/
COPY storage/ /app/storage/

# 暴露端口
EXPOSE ${AGENT_SERVICE_PORT:-8020}

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${AGENT_SERVICE_PORT:-8020}/health || exit 1

# 启动命令
CMD ["python", "-m", "app.agent.server"]
