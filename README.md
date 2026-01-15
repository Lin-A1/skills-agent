<div align="center">

# 🤖 Sage - Skills Agent

**基于 Skills 模式的智能 Agent 框架**  
**An Intelligent Agent Framework Based on Skills Pattern**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.x-green.svg)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-teal.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)

[English](#english) | [中文](#中文)

<img src="docs/images/main_interface.png" alt="Sage Interface" width="800"/>

</div>

---

## 中文

### 📖 项目简介

Sage 是一个基于 **Skills 模式** 的智能 Agent 框架，遵循 [Agent Skills](https://agentskills.io) 规范设计。

核心理念是将复杂的 Agent 能力拆解为可发现、可组合的 **技能（Skills）**，每个技能通过标准化的 `SKILL.md` 文件进行描述。Agent 在运行时自动发现这些技能，并根据用户需求动态调用，在隔离的沙盒环境中执行代码，最终完成复杂任务。

### ✨ 核心特性

#### 🎯 Skills Agent 架构设计

这是本项目的**核心创新点**，采用了类似 Claude Code 的 Agentic 设计模式：

##### 1. 技能自动发现 (Skill Auto-Discovery)

Agent 启动时自动扫描 `services/` 目录下的所有 `SKILL.md` 文件：

```
services/
├── websearch_service/
│   └── SKILL.md          ← 联网搜索技能
├── sandbox_service/
│   └── SKILL.md          ← 沙盒执行技能
├── deepsearch_service/
│   └── SKILL.md          ← 深度研究技能
├── rag_service/
│   └── SKILL.md          ← RAG 检索技能
└── ...
```

- 解析 YAML frontmatter 提取技能名称和描述
- 自动构建可用技能列表注入系统提示词
- 支持运行时刷新技能列表

##### 2. 标准化技能描述 (Standardized SKILL.md)

每个技能使用统一的 Markdown 格式描述：

```yaml
---
name: websearch-service
description: 基于 SearXNG 与 VLM 的实时联网搜索服务
---

## 功能
通过 SearXNG 搜索引擎获取网页结果，使用 VLM 进行智能分析...

## 调用方式
```python
from services.websearch_service.client import WebSearchClient
client = WebSearchClient()
result = client.search("Python async编程", max_results=5)
```

## 返回格式
{ "query": "...", "results": [...] }
```

##### 3. 沙盒隔离执行 (Sandbox Isolation)

所有技能代码在 Docker 沙盒中安全执行，Agent 本身不依赖任何技能环境：

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Engine                            │
│  ┌────────────────┐         ┌─────────────────────────────┐ │
│  │ Skill Registry │         │       LLM Service           │ │
│  │ (自动发现技能)  │         │   (思考 & 生成代码)         │ │
│  └───────┬────────┘         └─────────────────────────────┘ │
│          │                                                   │
│          ▼                                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  Skill Executor                        │  │
│  │     ┌─────────────────────────────────────────────┐   │  │
│  │     │         Sandbox Service (Docker)             │   │  │
│  │     │  ┌─────────────────────────────────────────┐│   │  │
│  │     │  │ • 网络隔离 / 资源限制 / 超时控制        ││   │  │
│  │     │  │ • trusted_mode: 访问内部服务网络        ││   │  │
│  │     │  │ • 执行后自动销毁，无状态残留            ││   │  │
│  │     │  └─────────────────────────────────────────┘│   │  │
│  │     └─────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**安全限制：**
- 内存限制：256MB
- CPU 限制：1 核
- 执行超时：60 秒
- 非 root 用户执行

##### 4. 多轮技能调用 (Multi-Turn Invocation)

支持一次回答中多次调用不同技能，形成**思考-执行-分析**的智能循环：

```
用户问题
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    迭代循环                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │  思考     │ →  │ 调用技能  │ →  │ 分析结果  │ ─┐      │
│  │ Thinking │    │ Execute  │    │ Analyze  │  │      │
│  └──────────┘    └──────────┘    └──────────┘  │      │
│       ▲                                         │      │
│       └─────────── 需要更多信息 ─────────────────┘      │
│                                                         │
│                    ↓ 信息充足                           │
└─────────────────────────────────────────────────────────┘
    │
    ▼
最终回答
```

##### 5. 流式事件输出 (Streaming Events)

实时展示 Agent 的思考和执行过程：

| 事件类型 | 说明 |
|---------|------|
| `THINKING` | Agent 正在思考分析 |
| `SKILL_CALL` | 准备调用某个技能 |
| `CODE_EXECUTE` | 正在执行代码 |
| `CODE_RESULT` | 代码执行结果 |
| `ANSWER` | 回答内容（流式） |
| `DONE` | 执行完成 |
| `ERROR` | 发生错误 |

### 🏗️ 系统架构

```
┌────────────────────────────────────────────────────────────────────┐
│                      Frontend (Vue 3 + Vite)                        │
│                      现代化聊天界面 & 推理过程可视化                   │
└────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                         Backend Services                            │
│  ┌─────────────────────────┐    ┌─────────────────────────┐        │
│  │     Chat Service         │    │     Agent Service        │        │
│  │     (Port 8006)          │    │     (Port 8009)          │        │
│  │   普通对话 & 会话管理      │    │   Skills 编排 & 执行      │        │
│  └─────────────────────────┘    └─────────────────────────┘        │
└────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                          Skills Layer                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │
│  │  WebSearch   │ │  DeepSearch  │ │   Sandbox    │ │    RAG     │ │
│  │  联网搜索     │ │  深度研究     │ │   代码执行    │ │  知识检索   │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                │
│  │  Embedding   │ │   Rerank     │ │     OCR      │                │
│  │  向量嵌入     │ │   重排序      │ │  图像识别     │                │
│  └──────────────┘ └──────────────┘ └──────────────┘                │
└────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                       Infrastructure                                │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                │
│  │  PostgreSQL  │ │    Milvus    │ │   SearXNG    │                │
│  │  会话存储     │ │  向量数据库   │ │   搜索引擎    │                │
│  └──────────────┘ └──────────────┘ └──────────────┘                │
└────────────────────────────────────────────────────────────────────┘
```

### 📁 项目结构

```
sage/
├── app/
│   ├── agent/                      # Agent 服务 (核心)
│   │   ├── core/
│   │   │   ├── agent_engine.py     # Agent 执行引擎
│   │   │   ├── skill_registry.py   # 技能注册表 (自动发现)
│   │   │   ├── skill_executor.py   # 技能执行器 (沙盒调用)
│   │   │   └── context_manager.py  # 上下文/记忆管理
│   │   ├── services/
│   │   │   ├── llm_service.py      # LLM 调用服务
│   │   │   └── agent_service.py    # Agent 业务逻辑
│   │   ├── api/routes.py           # API 路由
│   │   └── server.py               # FastAPI 入口
│   └── chat/                       # Chat 服务
│
├── services/                       # Skills 技能层
│   ├── websearch_service/          # 联网搜索
│   │   ├── SKILL.md               # 技能描述文件
│   │   ├── client.py              # Python 客户端
│   │   └── server.py              # 服务入口
│   ├── sandbox_service/            # 沙盒执行
│   ├── deepsearch_service/         # 深度研究
│   ├── rag_service/                # RAG 检索
│   ├── embedding_service/          # 向量嵌入
│   ├── rerank_service/             # 重排序
│   └── ocr_service/                # OCR 识别
│
├── web/frontend/                   # Vue 3 前端
├── docker-compose.yml              # Docker 编排
├── .env.example                    # 环境变量模板
└── README.md
```

### 🚀 快速开始

#### 1. 克隆项目

```bash
git clone https://github.com/your-repo/sage.git
cd sage
```

#### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env，填写 LLM API Key 等配置
```

#### 3. 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps
```

#### 4. 访问应用

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:5173 |
| Agent API | http://localhost:8009/docs |
| Chat API | http://localhost:8006/docs |

### 📚 API 使用示例

#### 流式调用 Agent

```python
import requests
import json

response = requests.post(
    "http://localhost:8009/api/agent/completions",
    json={
        "message": "帮我搜索一下 Python 异步编程的最佳实践",
        "stream": True
    },
    stream=True
)

for line in response.iter_lines():
    if line:
        data = line.decode('utf-8')
        if data.startswith("data: ") and data[6:] != "[DONE]":
            event = json.loads(data[6:])
            print(f"[{event['event_type']}] {event.get('content', '')}")
```

### 🔧 添加新技能

1. 在 `services/` 下创建新目录
2. 编写 `SKILL.md` 描述文件
3. 实现 `client.py` Python 客户端
4. 重启 Agent 服务或调用刷新 API

```bash
# 刷新技能列表
curl -X POST http://localhost:8009/api/agent/skills/refresh
```

---

## English

### 📖 Introduction

Sage is an intelligent Agent framework based on the **Skills Pattern**, designed following the [Agent Skills](https://agentskills.io) specification.

The core concept is to decompose complex Agent capabilities into discoverable and composable **Skills**, where each skill is described through a standardized `SKILL.md` file. The Agent automatically discovers these skills at runtime and dynamically invokes them based on user needs, executing code in an isolated sandbox environment to complete complex tasks.

### ✨ Core Features

#### 🎯 Skills Agent Architecture

This is the **core innovation** of this project, adopting an Agentic design pattern similar to Claude Code:

##### 1. Skill Auto-Discovery

The Agent automatically scans all `SKILL.md` files in the `services/` directory at startup:

```
services/
├── websearch_service/
│   └── SKILL.md          ← Web search skill
├── sandbox_service/
│   └── SKILL.md          ← Sandbox execution skill
├── deepsearch_service/
│   └── SKILL.md          ← Deep research skill
└── rag_service/
    └── SKILL.md          ← RAG retrieval skill
```

##### 2. Standardized SKILL.md Format

Each skill uses a unified Markdown format:

```yaml
---
name: websearch-service
description: Real-time web search service based on SearXNG and VLM
---

## Features
Fetches web results through SearXNG, uses VLM for intelligent analysis...

## Usage
```python
from services.websearch_service.client import WebSearchClient
client = WebSearchClient()
result = client.search("Python async programming", max_results=5)
```
```

##### 3. Sandbox Isolation

All skill code is executed safely in Docker sandbox. The Agent itself doesn't depend on any skill environment:

- Memory limit: 256MB
- CPU limit: 1 core
- Execution timeout: 60 seconds
- Non-root user execution
- `trusted_mode` for accessing internal service network

##### 4. Multi-Turn Skill Invocation

Supports multiple skill calls in a single response, forming an intelligent **Think-Execute-Analyze** loop:

```
User Question → Think → Execute Skill A → Analyze → Execute Skill B → Final Answer
                  ↑                                         ↓
                  └──────── Need more information ──────────┘
```

##### 5. Streaming Events

Real-time display of Agent's thinking and execution process:

| Event Type | Description |
|------------|-------------|
| `THINKING` | Agent is thinking/analyzing |
| `SKILL_CALL` | Preparing to call a skill |
| `CODE_EXECUTE` | Executing code |
| `CODE_RESULT` | Code execution result |
| `ANSWER` | Answer content (streaming) |
| `DONE` | Execution complete |
| `ERROR` | Error occurred |

### 🚀 Quick Start

#### 1. Clone Repository

```bash
git clone https://github.com/your-repo/sage.git
cd sage
```

#### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in LLM API keys
```

#### 3. Start Services

```bash
docker-compose up -d
```

#### 4. Access Application

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Agent API | http://localhost:8009/docs |
| Chat API | http://localhost:8006/docs |

### 📚 API Example

```python
import requests
import json

response = requests.post(
    "http://localhost:8009/api/agent/completions",
    json={
        "message": "Search for Python async programming best practices",
        "stream": True
    },
    stream=True
)

for line in response.iter_lines():
    if line:
        data = line.decode('utf-8')
        if data.startswith("data: ") and data[6:] != "[DONE]":
            event = json.loads(data[6:])
            print(f"[{event['event_type']}] {event.get('content', '')}")
```

---

## 📄 License

MIT License

---

<div align="center">

**Made with ❤️ by Lin**

</div>
