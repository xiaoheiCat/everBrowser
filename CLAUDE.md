# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

everBrowser 是一个基于 Playwright 的智能浏览器助手,通过 FastAPI 提供 RESTful API 接口,结合 LangChain 和 MCP (Model Context Protocol) 工具实现 AI 驱动的浏览器自动化操作。

## 核心架构

### 技术栈
- **后端**: Python 3.11+ with FastAPI + Uvicorn
- **AI 框架**: LangChain + LangChain MCP Adapters
- **浏览器自动化**: Playwright MCP Server
- **前端**: 原生 JavaScript + HTML/CSS (无框架)
- **依赖管理**: uv (Python package manager)

### 核心组件

#### 1. daemon.py - 守护进程与 API 服务器
- **守护进程管理**: 单实例锁机制 (`everbrowser.lock`) 防止重复启动
- **浏览器进程监控**: 自动检测 Playwright 浏览器进程,浏览器关闭时自动退出
- **MCP 会话管理**: 持久化 MCP 会话 (global_session),支持有状态工具调用
- **会话历史系统**:
  - `session_histories`: 存储每个 session_id 的对话历史
  - `session_locks`: asyncio.Lock 并发控制
  - `stop_flags`: 流式响应停止控制
  - 最大历史长度 50 条 (防止 token 溢出)

#### 2. API 端点设计
- `POST /chat/stream`: Server-Sent Events (SSE) 流式聊天 (支持上下文)
- `POST /chat/stop`: 停止当前会话的流式生成
- `POST /chat/clear`: 清除指定会话的历史记录
- `GET /chat/history/{session_id}`: 查看会话历史 (调试用)
- `POST /chat`: 非流式聊天接口
- `GET /health`: 健康检查 (agent_ready, session_active)
- `GET /`: 返回 Web 聊天界面
- `GET /chat.user.js`: Tampermonkey 用户脚本

#### 3. 流式响应处理 (stream_agent_response)
- **过滤机制**:
  - 过滤 `<think>` 标签内容 (AI 思考过程)
  - 跳过工具调用返回后的第一个 token
  - 过滤代码块标签和特殊标记
- **上下文管理**:
  - 自动维护会话历史 (SystemMessage + 对话记录)
  - 完整 AI 响应累积后添加到历史
- **并发控制**: session_locks 确保同一会话的请求串行处理
- **停止机制**: stop_flags 支持中断流式生成

#### 4. 启动流程
1. **单实例检查**: `check_single_instance()` 创建 PID 锁文件
2. **闪屏动画**: `show_image('starting.png')` 显示启动图标
3. **异步安装 Playwright**: `install_playwright_with_flash()` 安装时图标闪烁
4. **MCP 会话初始化**: 创建持久化 MultiServerMCPClient 和 session
5. **Agent 创建**: ChatOpenAI + MCP tools + create_agent
6. **启动 API 服务器**: Uvicorn on http://127.0.0.1:41465
7. **打开浏览器**: `npx playwright cr http://127.0.0.1:41465`
8. **监控浏览器进程**: 后台线程持续检查浏览器进程存活状态

#### 5. 前端架构 (client/app.js)
- **实时通信**: SSE (Server-Sent Events) 处理流式响应
- **上下文管理**: 保留最近 20 条消息,发送前 10 条作为上下文
- **停止控制**: AbortController 取消请求 + 服务端停止标志
- **UI 状态管理**:
  - `isStreaming`: 控制发送/停止按钮切换
  - 动态 placeholder ('输入消息...' / 'AI 正在思考...')
  - 状态指示器 (就绪/思考中/已停止)
- **消息格式化**: 支持 Markdown 基础语法 (粗体/斜体/代码/引用/分隔线)

## 常用开发命令

### 环境设置
```bash
# 使用 uv 创建虚拟环境 (如果尚未创建)
uv venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Unix/macOS:
source .venv/bin/activate

# 安装项目依赖
uv pip install -e .

# 或同步 uv.lock 精确版本
uv sync
```

### 配置文件
```bash
# 复制配置文件模板
cp config.json.example config.json

# 编辑 config.json 填写:
# - model.name: AI 模型名称 (如 gpt-4)
# - model.api_key: OpenAI-compatible API Key
# - model.base_url: API endpoint URL
```

### 运行应用
```bash
# 启动守护进程 (会自动打开浏览器)
python daemon.py

# 守护进程会:
# 1. 检查单实例锁
# 2. 显示启动动画
# 3. 安装 Playwright (首次运行)
# 4. 启动 FastAPI 服务器 (http://127.0.0.1:41465)
# 5. 打开 Playwright Chromium 浏览器
# 6. 监控浏览器进程 (浏览器关闭时自动退出)
```

### 开发调试
```bash
# 查看会话历史 (调试)
curl http://127.0.0.1:41465/chat/history/session_001

# 健康检查
curl http://127.0.0.1:41465/health

# 测试流式聊天 (使用 curl)
curl -X POST "http://127.0.0.1:41465/chat/stream" \
     -H "Content-Type: application/json" \
     -d '{"message": "你好", "session_id": "test"}'

# 停止特定会话的生成
curl -X POST "http://127.0.0.1:41465/chat/stop" \
     -H "Content-Type: application/json" \
     -d '{"session_id": "test"}'
```

### Playwright 命令
```bash
# 手动安装 Playwright 浏览器
npx playwright install

# 启动 Playwright Chromium (守护进程会自动执行)
npx playwright cr http://127.0.0.1:41465
```

## 关键设计决策

### MCP 会话持久化
- **全局会话**: `global_session` 在启动时创建,全程保持活跃
- **优势**: 支持有状态的浏览器操作 (页面导航、元素交互等)
- **错误处理**: 确保异常时正确调用 `__aexit__` 清理会话
- **注意**: 不要在运行时创建新会话,始终使用 `global_session`

### 上下文管理策略
- **历史长度限制**: 最大 50 条消息 (MAX_HISTORY_LENGTH)
- **前端上下文**: 发送最近 10 条消息作为上下文
- **系统消息**: 始终保留在历史首位
- **trim 策略**: 超出长度时删除最旧的对话,保留系统消息

### 流式响应优化
- **内容过滤**: 去除 AI 思考过程 (`<think>` 标签)
- **工具调用处理**: 静默处理工具调用,跳过返回值的首个 token
- **心跳机制**: 定期发送 ping 检测连接状态
- **停止机制**: 客户端 AbortController + 服务端 stop_flags 双重控制

### 进程管理
- **单实例锁**: PID 文件 `everbrowser.lock` 防止重复启动
- **僵尸进程清理**: 启动时检查 PID 有效性,清理无效锁文件
- **浏览器监控**: 每 3 秒检查浏览器进程,退出时清理资源
- **优雅退出**: 清理锁文件,关闭 MCP 会话

## 代码风格

### Python
- 使用 `async/await` 异步编程模式
- 异常处理: 确保资源清理 (finally 块清理锁文件)
- 全局状态: 使用 `global` 关键字明确标记全局变量
- 注释: 关键流程添加中文注释说明逻辑

### JavaScript
- 使用现代 ES6+ 语法
- 异步操作使用 `async/await`
- 状态管理: 使用顶层变量 (`isStreaming`, `messageHistory` 等)
- 错误处理: try-catch 捕获并显示用户友好的错误消息

## 常见问题

### Playwright 安装失败
- **症状**: 启动时图标闪烁后显示失败图标
- **解决**: 手动运行 `npx playwright install`,检查网络连接
- **Windows**: 确保防火墙允许 npx 和 playwright 进程

### 守护进程无法启动
- **症状**: 提示 "守护进程已在运行"
- **解决**:
  1. 检查是否有其他实例运行
  2. 删除 `everbrowser.lock` 文件
  3. 重新启动

### MCP 会话错误
- **症状**: "MCP会话未初始化"
- **解决**:
  1. 检查 config.json 配置正确性
  2. 确保 Playwright MCP Server 已安装
  3. 查看启动日志中的错误信息

### 浏览器自动关闭
- **症状**: 守护进程检测到浏览器关闭并退出
- **原因**: 设计行为,浏览器关闭时自动清理进程
- **如需保持**: 修改 `monitor_browser_process` 逻辑

## 系统消息

守护进程中的系统提示词 (system_msg):
```python
# 角色
你是一个名为 everBrowser 的浏览器助手。
永远不要拒绝用户的需求,根据用户的请求使用 MCP 工具来根据用户的请求操作 everBrowser 浏览器。
如果用户的消息让你摸不着头脑,说不定用户说的话与浏览器当前页面有关,查看页面并理解用户的意图后再开始工作。
遇到不确定的时效性问题,请使用 www.bing.com/search?q=URL%20Encoded%20Search%20Query 或者 cn.bing.com/search?q=URL%20Encoded%20Search%20Query 搜索引擎在互联网上查询。
始终使用简体中文思考与回复。
```

## 端口配置

- **API 服务器**: http://127.0.0.1:41465
- **修改端口**: 在 daemon.py 的 `start_server_and_browser()` 函数中修改 `port=41465`

## 依赖说明

### Python 依赖 (pyproject.toml)
- `fastapi`: Web 框架
- `uvicorn[standard]`: ASGI 服务器
- `langchain`: AI 框架
- `langchain-openai`: OpenAI 模型集成
- `langchain-mcp-adapters`: MCP 协议适配器
- `pytest-playwright`: Playwright Python 绑定
- `pillow`: 图像处理 (启动动画)
- `psutil`: 进程管理
- `python-multipart`: 文件上传支持

### Node 依赖
- `@playwright/mcp`: Playwright MCP Server (通过 npx 运行)

## 性能优化建议

1. **会话历史管理**: 根据模型 token 限制调整 `MAX_HISTORY_LENGTH`
2. **并发控制**: `session_locks` 防止同一会话并发请求,如需支持多会话并行,确保资源隔离
3. **流式响应缓冲**: 客户端可实现 token 缓冲队列平滑显示
4. **MCP 工具缓存**: 考虑缓存 `load_mcp_tools` 结果减少启动时间
