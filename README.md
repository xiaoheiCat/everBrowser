# everBrowser

> 让浏览变得更简单

## 🌟 项目简介

everBrowser 是一个基于 Chromium 和 Playwright 的轻量级、高性能的 AI Agent 浏览器。

## ✨ 核心特性

- **稳定可靠** - 经过长时间运行测试，能够持续稳定地为用户提供服务
- **轻量高效** - 精心优化的代码结构，占用资源少，响应速度快
- **跨平台支持** - 支持主流操作系统，让用户无后顾之忧
- **简洁易用** - 直观的用户界面，降低学习成本

## 🚀 快速开始

### 环境要求

- Python 3.8+
- uv 0.1.0+
- Node.js 18+

### 安装步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/xiaoheiCat/everBrowser.git
   cd everBrowser
   ```

2. **安装依赖**
   ```bash
   # 我们推荐使用 uv 进行依赖管理
   uv venv && uv sync
   ```

3. **配置项目**
   ```bash
   cp config.json.example config.json
   # 根据您的需求编辑 config.json
   ```

4. **启动服务**
   ```bash
   uv run daemon.py
   ```

## 📖 使用说明

### 基本用法

启动服务后，浏览器会自动安装并启动。然后，系统会自动打开用户聊天界面。

### 指示灯

您可能经常在项目中见到 everBrowser 的[图标](icon.png)。以下是它们的含义：
- 常亮的 Ever 图标 + 右下角的“加载中”图标: 服务正在启动
- 闪烁的 Ever 图标 + 右下角的“加载中”图标: 浏览器正在安装或者更新
- 闪烁的 Ever 图标 + 右下角的“警告”图标: 启动时遇到了一点问题 (请检查 Node.js 18+ 是否安装、网络是否通畅、配置文件是否设置)

### 卸载

在终端中执行以下命令:

```bash
npx playwright uninstall
```

然后删除 Clone 的 Git 仓库即可。

### 配置选项

项目提供了高度可自定义的 LLM AI 配置选项，您可以在 `config.json` 中进行设置：

```json
{
  "model": {
    "name": "your_model_name",
    "api_key": "your_api_key",
    "base_url": "your_base_url"
  }
}
```

## 🛠️ 开发指南

### 项目结构

```
everBrowser/
├── daemon.py          # 主守护进程
├── client/            # 前端资源
│   ├── index.html     # 主页面
│   ├── style.css      # 样式文件
│   └── app.js         # 前端逻辑
├── config.json        # 配置文件
└── README.md          # 项目文档
```

### 开发环境搭建

1. **Fork 项目** 到您的 GitHub 账户
2. **创建功能分支** (`git checkout -b feature/amazing-feature`)
3. **提交更改** (`git commit -m 'Add some amazing feature'`)
4. **推送到分支** (`git push origin feature/amazing-feature`)
5. **创建 Pull Request**

### 代码规范

我们遵循简洁明了的代码风格：

- 使用有意义的变量名和函数名
- 添加必要的注释说明复杂逻辑
- 保持代码结构清晰，避免过度工程化

## 📄 许可证

本项目采用 GNU General Public License v3.0 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。

## 🤝 贡献指南

虽然我们只是一个小项目，但我们欢迎任何形式的贡献：

1. **发现问题** - 如果您发现了bug，请提交Issue
2. **功能建议** - 有好的想法？我们很乐意听取您的建议
3. **代码贡献** - 欢迎提交Pull Request
4. **文档改进** - 帮助我们改进文档质量

### 贡献者

感谢所有为项目做出贡献的朋友们，是你们的支持让这个项目变得更好。

## 🙏 致谢

- 感谢开源社区提供的优秀工具和库
- 感谢用户们的反馈和建议
- 感谢每一位贡献者的时间和精力

### 👍 支持我们

在 everBrowser 发起以下对话:
```plaintext
请在 GitHub 上找到用户 xiaoheiCat 主页中的 everBrowser 仓库，并给她点一个 Star ✨
```

---

> 💡 **小提示**: 如果您在使用过程中遇到任何问题，请不要犹豫向我们反馈。我们虽然能力有限，但会尽力为每一位用户提供帮助。

> ⚠️ **免责声明**: 这是一个持续改进中的项目，可能存在一些不足之处。我们承诺会持续优化，但进度可能会比较缓慢，敬请谅解。

---

*Made with ❤️ by xiaoheiCat*
