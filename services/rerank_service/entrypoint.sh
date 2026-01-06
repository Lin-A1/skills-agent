#!/bin/bash
python3 -m vllm.entrypoints.openai.api_server \
    --model "${RERANK_MODEL_NAME:-Qwen/Qwen3-Reranker-0.6B}" \
    --host 0.0.0.0 \
    --port "${RERANK_PORT:-8003}" \
    --trust-remote-code \
    --gpu-memory-utilization 0.25 \
    --max-model-len 1024 \
    --max-num-seqs 16
