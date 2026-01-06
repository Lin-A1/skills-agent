#!/bin/bash
python3 -m vllm.entrypoints.openai.api_server \
    --model "${EMBEDDING_MODEL_NAME:-Qwen/Qwen3-Embedding-0.6B}" \
    --host 0.0.0.0 \
    --port "${EMBEDDING_PORT:-8002}" \
    --trust-remote-code \
    --gpu-memory-utilization 0.25 \
    --max-model-len 2048 \
    --max-num-seqs 32
