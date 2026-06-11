# GitHub AI 热门项目日报

这个工具通过 GitHub Actions 每天 09:00（北京时间）抓取 GitHub 上最近创建并较热门的 AI 应用工具项目，调用火山方舟 Claude / Anthropic 兼容接口生成中文摘要，然后发送到飞书群机器人。

项目重点关注 MCP、Agent、插件、Skill、Claude Code、Codex、CLI、编辑器扩展等开箱即用工具；搜索时会排除课程、教程、论文、数据集、benchmark 等学习或研究类内容。

## GitHub 搜索规则

当前关键词包括：

```text
mcp
model-context-protocol
ai-agent
agent
claude-code
codex
plugin
plugins
skill
skills
automation
developer-tools
cli
vscode-extension
cursor
```

每个关键词会限制：

```text
created:>=最近14天
stars:>20
```

并排除以下学习或研究类内容：

```text
course
tutorial
awesome
paper
papers
dataset
benchmark
study
learning
```

## GitHub Secrets

在仓库 `Settings -> Secrets and variables -> Actions` 中添加：

```text
ARK_ANTHROPIC_AUTH_TOKEN
ARK_ANTHROPIC_BASE_URL
ARK_ANTHROPIC_MODEL
FEISHU_WEBHOOK_URL
```

可选：

```text
ARK_ANTHROPIC_VERSION
ARK_ANTHROPIC_API_KEY
FEISHU_WEBHOOK_SECRET
```

如果飞书机器人开启了签名校验，必须配置 `FEISHU_WEBHOOK_SECRET`。

火山方舟 Claude Code / Anthropic 兼容接口通常使用 `ANTHROPIC_AUTH_TOKEN`。为了兼容其他 Anthropic 协议服务，workflow 也支持用 `ARK_ANTHROPIC_API_KEY` 作为备用 secret。
使用 `ARK_ANTHROPIC_AUTH_TOKEN` 时，脚本会通过 `Authorization: Bearer <token>` 鉴权；使用备用 `ARK_ANTHROPIC_API_KEY` 时，脚本会通过 `x-api-key` 鉴权。

`ARK_ANTHROPIC_BASE_URL` 建议填写到服务根路径，例如：

```text
https://ark.cn-beijing.volces.com/api/coding
```

脚本会自动请求 `/v1/messages`。

## GitHub Variables

可选变量：

```text
REPORT_REPO_LIMIT=8
```

## 手动测试

配置完 Secrets 后，在 GitHub 仓库页面进入：

```text
Actions -> Daily AI GitHub Report -> Run workflow
```

如果运行成功，飞书群会收到一条中文项目日报。

## 本地测试

```bash
python3 -m unittest tests/test_daily_ai_github_report.py
```

本地真实发送需要先设置同名环境变量。
