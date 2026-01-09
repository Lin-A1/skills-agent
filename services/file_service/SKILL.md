---
name: file_service
description: 文件操作服务，支持在共享工作区读写文件。Agent可以使用此服务创建文件，然后让 Sandbox 执行代码读取这些文件。
client_class: FileServiceClient
default_method: list_files
---

## 功能
提供对 `/workspace` 目录的文件读写访问。

## 适用场景
- Agent 需要创建数据文件供代码分析使用
- 读取 Sandbox 代码执行生成的输出文件
- 管理工作区文件

## 调用方式
```python
from services.file_service.client import FileServiceClient

client = FileServiceClient()

# 列出文件
files = client.list_files()

# 写入文件
client.write_file("test.txt", "hello world")

# 读取文件
content = client.read_file("test.txt")
```
