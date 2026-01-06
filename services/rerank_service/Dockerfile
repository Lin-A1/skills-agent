FROM vllm/vllm-openai:v0.8.5.post1

# 设置工作目录
WORKDIR /app

# 设置模型缓存目录和ModelScope镜像源
ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models
ENV MODELSCOPE_CACHE=/app/models
ENV HF_ENDPOINT=https://hf-mirror.com
ENV USE_MODELSCOPE_HUB=1

# 创建模型目录
RUN mkdir -p /app/models

# 复制启动脚本
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 暴露端口（默认8002，可通过环境变量覆盖）
EXPOSE ${RERANK_PORT:-8003}

# 启动vLLM服务
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"] 
