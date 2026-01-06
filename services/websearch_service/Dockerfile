FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    fonts-liberation \
    fonts-noto-cjk \
    \
    libnss3 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxext6 \
    libxfixes3 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libxshmfence1 \
    libxkbcommon0 \
    libdrm2 \
    libglib2.0-0 \
    libgtk-3-0 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir \
    playwright \
    fastapi \
    uvicorn \
    python-dotenv \
    openai \
    httpx \
    sqlalchemy \
    psycopg2-binary \
    pymilvus \
    requests

RUN playwright install chromium

COPY . /app/

EXPOSE ${SEARCH_SERVICE_PORT:-8004}

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${SEARCH_SERVICE_PORT:-8004}/health || exit 1

CMD ["python", "server.py"]