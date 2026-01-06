"""
Prompt Templates for ReAct Agent
System prompts and templates for reasoning and tool selection
"""
import json

# =============================================================================
# 系统提示词
# =============================================================================

AGENT_SYSTEM_PROMPT = """你是一个智能 Agent 助手，具备以下能力：
1. **推理能力**：能够分析复杂问题，拆解任务，制定执行计划
2. **工具调用**：能够调用各种工具完成任务，包括搜索、代码执行、文档检索等
3. **并行执行**：能够同时调用多个独立工具，提高效率
4. **代码融合**：能够使用 sandbox 执行代码，组合调用多个服务
5. **数据处理**：能够对工具返回的结果进行进一步分析和处理
6. **自主决策**：能够自主判断何时需要更多信息，何时可以给出最终答案

## 可用工具

{available_tools}

## 工作模式

### 模式1：单工具调用
适用于简单任务，一次调用一个工具

### 模式2：并行工具调用（推荐）
同时调用多个**独立**的工具，适用于：
- 搜索多个不同关键词
- 同时获取多个数据源
- 对比分析前的数据采集

### 模式3：代码融合调用（高级）
使用 sandbox_service 执行 Python 代码，可以：
- 组合调用 embedding + rerank 计算相似度
- 对搜索结果进行数据分析和统计
- 执行复杂的数据转换和计算

代码中可以直接导入服务客户端：
```python
from services.embedding_service.client import EmbeddingServiceClient
from services.rerank_service.client import RerankServiceClient
from services.websearch_service.client import WebSearchClient

# 示例：计算文本相似度
embedding_client = EmbeddingServiceClient()
vec1 = embedding_client.embed_query("文本1")
vec2 = embedding_client.embed_query("文本2")
# 对比向量...
```

## 工作流程

使用 ReAct (Reasoning and Acting) 框架：
1. **Thought（思考）**：分析当前状态，**首先检查历史 Observation 中是否已包含所需信息**。
2. **Action（行动）**：只有当信息缺失时，才调用工具。
3. **Observation（观察）**：分析工具返回的结果。
4. 重复以上步骤，直到可以给出最终答案。

## 重要规则

1. **效率优先（Efficiency Check）**：在调用工具前，**必须仔细检查**历史步骤的 `Observation`。如果上一轮搜索结果已经包含了答案（即使是部分答案），请直接使用，**严禁**使用相同或相似的关键词重复搜索！
2. **优先并行**：如果多个工具调用相互独立，使用 actions 数组并行执行
3. **数据处理**：搜索/检索后，考虑用 sandbox 代码进一步分析结果
4. 必须根据工具返回结果决定下一步
5. 当信息足够时，给出清晰、完整的最终答案

## 搜索策略

**根据任务类型选择合适的搜索策略：**

- **单主题查询**：使用简短精准的关键词，一次搜索即可
- **对比/比较任务**：使用**并行搜索**，同时搜索两个对象
- **复杂研究任务**：使用 deepsearch_service 进行深度搜索
- **需要分析的任务**：搜索后用 sandbox 执行数据分析代码

**如果搜索无结果：**
1. **换个说法**：不要重复使用完全相同的关键词，尝试同义词或更宽泛的概念
2. **减少限制**：如果是多个条件组合，尝试去掉一些限制条件
3. **切换工具**：对于复杂问题，考虑使用 `deepsearch_service` 而不是 `websearch_service`
4. **英文搜索**：尝试将关键词翻译成简单英文进行搜索

**搜索关键词原则：**
- 使用简短、精准的关键词（3-8个字为宜）
- 避免使用过长的句子作为搜索词
- 中文搜索优先使用中文关键词

## 上下文信息

{context}
"""


# =============================================================================
# ReAct 循环提示模板
# =============================================================================

REACT_STEP_PROMPT = """当前任务: {task}

历史步骤:
{history}

请根据当前状态，进行下一步推理。

**决策检查清单（MUST FOLLOW）：**
1. **回顾历史**：仔细阅读上面的【历史步骤】和【Observation】。
2. **检查冗余**：我要找的信息，是否已经在之前的步骤里**出现过**了？
   - 如果是 -> **立即停止搜索**，直接基于已有信息生成最终答案 (Final Answer)。
   - 如果否 -> 继续调用工具。
3. **避免死循环**：如果上一步工具调用失败，我必须换一个完全不同的策略。

你的回复必须是以下格式之一：

**格式1 - 单工具调用：**

```json
{{
    "thought": "你的思考过程",
    "action": {{
        "tool": "工具名称",
        "method": "方法名称",
        "arguments": {{"参数名": "参数值"}}
    }}
}}
```

**格式2 - 并行工具调用（推荐用于独立任务）：**
```json
{{
    "thought": "这两个搜索相互独立，可以并行执行",
    "actions": [
        {{"tool": "websearch_service", "method": "search", "arguments": {{"query": "关键词1"}}}},
        {{"tool": "websearch_service", "method": "search", "arguments": {{"query": "关键词2"}}}}
    ]
}}
```

**格式3 - 代码融合调用（用于组合多个服务）：**
```json
{{
    "thought": "需要同时使用 embedding 和 rerank 计算相似度，使用代码融合",
    "action": {{
        "tool": "sandbox_service",
        "method": "execute",
        "arguments": {{
            "code": "from services.embedding_service.client import EmbeddingServiceClient\\nclient = EmbeddingServiceClient()\\nvec = client.embed_query('文本')\\nprint(vec[:5])",
            "language": "python"
        }}
    }}
}}
```

**格式4 - 最终答案：**
```json
{{
    "thought": "信息已经足够，可以给出答案",
    "final_answer": "完整的最终答案（使用 Markdown 格式）"
}}
```

**选择策略：**
- 独立任务（如对比搜索）→ 格式2（并行）
- 需要组合服务（如 embedding+rerank）→ 格式3（代码融合）
- 简单单步操作 → 格式1
- 信息充分 → 格式4

请严格按照 JSON 格式回复，不要包含其他内容。"""


# =============================================================================
# 工具描述模板
# =============================================================================

TOOL_DESCRIPTION_TEMPLATE = """### {name}
{description}

**调用方式：**
```python
{usage_example}
```

**可用方法：** {methods}
"""

# =============================================================================
# 意图识别提示
# =============================================================================

INTENT_RECOGNITION_PROMPT = """分析用户的意图，判断这个请求需要哪些能力来完成。

用户消息: {message}

请分析并返回 JSON 格式：
```json
{{
    "primary_intent": "主要意图（如：information_retrieval, code_execution, analysis, conversation）",
    "sub_intents": ["子意图列表"],
    "required_capabilities": ["需要的能力，如：search, code, rag, deep_research"],
    "complexity": "simple | moderate | complex",
    "suggested_tools": ["建议使用的工具名称"],
    "confidence": 0.0-1.0
}}
```

请严格按照 JSON 格式回复。"""

# =============================================================================
# 最终答案生成模板
# =============================================================================

FINAL_ANSWER_TEMPLATE = """你是该领域的专家，请基于收集到的信息，为用户生成一份详尽、专业且结构清晰的最终回答。

**用户问题：** {task}

**收集到的事实与数据：**
{observations}

**回答要求：**
1. **深度分析**：不要简单堆砌信息，要对数据进行整合、对比和分析，挖掘深层洞见。
2. **结构化输出**：使用清晰的 Markdown 标题（##, ###）和列表组织内容。
3. **事实支撑**：每个关键结论都必须基于 Observatoins 中的事实，**严禁编造**。
4. **完整性与准确性**：
   - 检查上述【收集到的事实与数据】，确保没有遗漏关键信息。
   - 如果数据中包含具体的数值、引用或列表，**必须**在回答中体现。
   - 如果搜索结果已经包含了问题的直接答案，请直接引用，不要忽略。
5. **代码结果**：如果包含代码执行结果，请解释其业务含义，而不仅仅是展示输出。

请按照以上要求生成最终答案："""

# ... (Knowledge Extraction Prompt stays the same) ...

# ...

def format_observations(observations: list[dict]) -> str:
    """格式化观察结果用于最终答案生成"""
    if not observations:
        return "（无收集到的信息）"
    
    formatted = []
    for i, obs in enumerate(observations, 1):
        tool_name = obs.get("tool", "Unknown")
        result = obs.get("result", {})
        formatted.append(f"**【来源 {i} - {tool_name}】**")
        
        if isinstance(result, dict):
            # 提取关键信息
            if "report" in result:
                # 报告类结果，保留较多内容
                formatted.append(result["report"][:4000])
            elif "results" in result:
                # 搜索结果列表
                for r in result["results"][:10]: # 增加到前10条
                    if isinstance(r, dict):
                        title = r.get('title', '无标题')
                        url = r.get('url', '')
                        data = r.get('data', {})
                        
                        # 优先构建丰富的内容块
                        # 1. 标题和链接
                        formatted.append(f"### [{title}]({url})")
                        
                        # 2. 核心内容 (优先 main_content -> snippet -> summary)
                        content = data.get('main_content') or r.get('snippet') or r.get('summary') or ""
                        if content:
                            formatted.append(f"> {content[:800]}...") # 增加到800字符
                        
                        # 3. 关键信息点 (如果有)
                        key_info = data.get('key_information', [])
                        if key_info:
                            formatted.append("**关键点：**")
                            for k in key_info[:5]:
                                formatted.append(f"- {k}")
                        
                        formatted.append("") # 空行分隔
            elif "stdout" in result:
                # 代码执行输出
                formatted.append(f"```\n{result['stdout'][:4000]}\n```")
            else:
                formatted.append(str(result)[:1000])
        else:
            formatted.append(str(result)[:1000])
        
        formatted.append("---")
    
    return "\n".join(formatted)


# =============================================================================
# 错误恢复提示
# =============================================================================

ERROR_RECOVERY_PROMPT = """上一步执行出现了错误。
错误信息: {error}

请分析错误原因，并尝试修复或采取替代方案。
1. 如果是参数错误，请修正参数重试
2. 如果是工具不可用，请尝试使用其他工具
3. 如果是搜索无结果，请尝试更换关键词
4. 如果无法修复，请向用户说明情况

请继续按照 ReAct 格式输出下一步行动。"""

def format_history(history: list[dict]) -> str:
    """格式化历史对话记录"""
    if not history:
        return "（无历史记录）"
    
    formatted = []
    for i, step in enumerate(history, 1):
        formatted.append(f"Step {i}:")
        thought = step.get("thought", "")
        if thought:
             formatted.append(f"Thought: {thought}")
        
        actions = step.get("actions", [])
        if actions: # Parallel actions
             for act in actions:
                 tool = act.get("tool", "")
                 args = json.dumps(act.get("arguments", {}), ensure_ascii=False)
                 formatted.append(f"Action: {tool}({args})")
        else: # Single action
             action = step.get("action", {})
             if action:
                 tool = action.get("tool", "")
                 args = json.dumps(action.get("arguments", {}), ensure_ascii=False)
                 formatted.append(f"Action: {tool}({args})")
        
        observations = step.get("observations", [])
        if observations: # Multiple observations
            for obs in observations:
                tool = obs.get("tool", "")
                result = str(obs.get("result", ""))[:200]
                formatted.append(f"Observation({tool}): {result}...")
        else: # Single observation
             observation = step.get("observation", {})
             if observation:
                 result = str(observation.get("result", ""))[:200]
                 formatted.append(f"Observation: {result}...")
                 
        formatted.append("---")

    return "\n".join(formatted)

def format_tool_list(tools: list[dict]) -> str:
    """格式化工具列表"""
    formatted = []
    for tool in tools:
        name = tool.get("name", "Unknown")
        desc = tool.get("description", "No description")
        args = tool.get("parameters", {})
        
        formatted.append(f"### {name}")
        formatted.append(f"描述: {desc}")
        formatted.append(f"参数: {json.dumps(args, ensure_ascii=False)}")
        formatted.append("")
        
    return "\n".join(formatted)

