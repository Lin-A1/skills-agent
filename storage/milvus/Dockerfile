FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装依赖
RUN apt-get update && apt-get install -y socat && rm -rf /var/lib/apt/lists/*

# 安装 Python 包
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --upgrade pip && \
    pip install --no-cache-dir numpy requests pyarrow minio azure-storage-blob pandas pymilvus milvus-lite

# 创建数据目录
RUN mkdir -p /var/lib/milvus/data

# 创建启动脚本 (Python)
RUN echo 'import os, time, sys; from milvus_lite.server import Server; s = Server("/var/lib/milvus/data/milvus.db"); s.start(); time.sleep(2); print(f"Addr={s._address} UDS={s.uds_path}"); res = str(s._address.split(":")[-1]) if s._address else f"UDS:{s.uds_path}" if s.uds_path else "ERROR"; f = open("/tmp/milvus_port", "w"); f.write(res); f.close();\nwhile True: time.sleep(10)' > /app/run_milvus.py

# 创建 Entrypoint 脚本：启动 Python Server 并用 socat 转发端口
RUN echo '#!/bin/bash\n\
    python3 /app/run_milvus.py &\n\
    echo "Waiting for Milvus to start..."\n\
    timeout=30\n\
    while [ ! -f /tmp/milvus_port ] && [ $timeout -gt 0 ]; do\n\
    sleep 1\n\
    ((timeout--))\n\
    done\n\
    if [ ! -f /tmp/milvus_port ]; then\n\
    echo "Milvus failed to start"\n\
    exit 1\n\
    fi\n\
    result=$(cat /tmp/milvus_port)\n\
    if [[ "$result" == "ERROR" ]]; then\n\
    echo "Milvus failed to provide address or UDS"\n\
    exit 1\n\
    fi\n\
    if [[ "$result" == UDS:* ]]; then\n\
    UDS_PATH=${result#UDS:}\n\
    UDS_PATH=${UDS_PATH#unix:}\n\
    echo "Forwarding 0.0.0.0:19530 -> UNIX:$UDS_PATH"\n\
    exec socat -d -d TCP-LISTEN:19530,fork,reuseaddr,bind=0.0.0.0 UNIX-CONNECT:"$UDS_PATH"\n\
    else\n\
    echo "Forwarding 0.0.0.0:19530 -> 127.0.0.1:$result"\n\
    exec socat -d -d TCP-LISTEN:19530,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:$result\n\
    fi' > /entrypoint.sh && \
    chmod +x /entrypoint.sh && \
    ln -sf /entrypoint.sh /usr/local/bin/milvus

# 暴露端口
EXPOSE 19530

# 启动命令
CMD ["/entrypoint.sh"]
