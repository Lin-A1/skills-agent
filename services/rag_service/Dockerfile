FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 配置 pip 镜像
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-dotenv \
    httpx \
    requests \
    pymilvus \
    pydantic

# 复制代码
COPY . /app

# 暴露端口
EXPOSE 8008

# 启动命令
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8008", "--reload"]
