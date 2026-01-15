# Agent Service

基于 [Agent Skills](https://agentskills.io) 模式的智能代理服务。

## 核心特性

### 1. Skills 集成
- 自动发现 `services/*/SKILL.md` 文件
- 在启动时解析 YAML frontmatter 提取 `name` 和 `description`
- 按需加载完整 skill 内容

### 2. Sandbox 执行
- 所有 skill 代码通过 `sandbox_service` 执行
- 使用 `trusted_mode=True` 允许访问其他服务
- Agent 不依赖任何 skill 的环境

### 3. 多轮调用
- 支持一次回答中多次调用 skills
- Agent 可以读取 SKILL.md -> 生成代码 -> 执行 -> 分析结果 -> 继续

### 4. 持久化记忆
- 会话级记忆（facts, preferences, context）
- 支持 TTL 过期机制
- 数据库持久化

### 5. 流式输出
- 实时返回思考过程
- 技能调用和执行结果事件
- 最终回答流式输出

## 目录结构

```
app/agent/
├── __init__.py
├── Dockerfile
├── README.md
├── config.py                    # 配置管理（含日期信息）
├── database.py                  # 数据库适配器
├── server.py                    # FastAPI 入口
├── api/
│   ├── __init__.py
│   └── routes.py               # API 路由
├── core/
│   ├── __init__.py
│   ├── skill_registry.py       # Skill 注册表
│   ├── skill_executor.py       # Skill 执行器
│   ├── context_manager.py      # 上下文/记忆管理
│   └── agent_engine.py         # Agent 引擎
├── schemas/
│   └── __init__.py             # Pydantic 模型
└── services/
    ├── __init__.py
    ├── llm_service.py          # LLM 服务
    └── agent_service.py        # Agent 业务逻辑
```

## API 端点

### Sessions
- `POST /api/agent/sessions` - 创建会话
- `GET /api/agent/sessions` - 列出会话
- `GET /api/agent/sessions/{id}` - 获取会话
- `PUT /api/agent/sessions/{id}` - 更新会话
- `DELETE /api/agent/sessions/{id}` - 删除会话

### Messages
- `GET /api/agent/sessions/{id}/messages` - 获取消息历史
- `DELETE /api/agent/sessions/{id}/messages` - 清空消息

### Agent Completion
- `POST /api/agent/completions` - Agent 执行（支持流式）

### Memories
- `POST /api/agent/sessions/{id}/memories` - 设置记忆
- `GET /api/agent/sessions/{id}/memories` - 获取记忆
- `DELETE /api/agent/sessions/{id}/memories/{key}` - 删除记忆

### Skills
- `GET /api/agent/skills` - 列出技能
- `GET /api/agent/skills/{name}` - 获取技能详情
- `POST /api/agent/skills/refresh` - 刷新技能列表

## 使用示例

### 流式调用

```python
import requests
import json

response = requests.post(
    "http://localhost:8009/api/agent/completions",
    json={
        "message": "请搜索一下 Python 异步编程的最佳实践",
        "stream": True
    },
    stream=True
)

for line in response.iter_lines():
    if line:
        data = line.decode('utf-8')
        if data.startswith("data: "):
            event_data = data[6:]
            if event_data != "[DONE]":
                event = json.loads(event_data)
                print(f"[{event['event_type']}] {event.get('content', '')}")
```

### 非流式调用

```python
response = requests.post(
    "http://localhost:8009/api/agent/completions",
    json={
        "message": "请帮我分析这段代码的性能问题",
        "stream": False
    }
)

result = response.json()
print(result["content"])
print(f"使用的技能: {result['skills_used']}")
```

## 配置

环境变量（在 `.env` 中配置）:

```env
# Agent 服务
AGENT_SERVICE_PORT=8009
AGENT_SERVICE_HOST=0.0.0.0
AGENT_SERVICE_DEBUG=true

# Agent LLM
AGENT_LLM_MODEL_NAME=mimo-v2-flash
AGENT_LLM_URL=https://api.xiaomimimo.com/v1
AGENT_LLM_API_KEY=sk-xxx

# Agent 参数
AGENT_DEFAULT_TEMPERATURE=0.3
AGENT_DEFAULT_MAX_TOKENS=4096
AGENT_MAX_ITERATIONS=10

# Skills
SKILLS_DIRECTORY=/app/services

# Sandbox
SANDBOX_SERVICE_HOST=sandbox_service
SANDBOX_SERVICE_PORT=8010
```

## 系统提示词

Agent 的系统提示词包含：
1. **当前日期时间** - 自动注入
2. **可用技能列表** - 从 SKILL.md 自动发现
3. **会话记忆** - 持久化存储的上下文
4. **执行规则** - 如何调用技能和分析结果

## 技能调用格式

Agent 使用以下 XML 格式调用技能:

```xml
<execute_skill>
<skill_name>sandbox-service</skill_name>
<code>
from services.deepsearch_service.client import DeepSearchClient

client = DeepSearchClient()
result = client.search("Python异步编程最佳实践")
print(result["report"])
</code>
</execute_skill>
```

## 依赖服务

- **PostgreSQL** - 会话和消息存储
- **Sandbox Service** - 代码执行
- **其他 Services** - 通过 Sandbox 的 trusted_mode 访问
