# GitHub AI 热门项目日报

每天 09:00（北京时间）通过 GitHub Actions 抓取 GitHub 上最近创建并较热门的 AI 应用工具项目，调用火山方舟 Claude / Anthropic 兼容接口生成中文摘要，然后发送到飞书群机器人。

项目重点关注 MCP、Agent、插件、Skill、Claude Code、Codex、CLI、编辑器扩展等开箱即用工具。搜索会先查最近创建且较热门的项目，如果没有候选项目，会自动扩大时间和活跃度范围兜底。

## 部署

在 GitHub 仓库 `Settings -> Secrets and variables -> Actions` 中添加：

```text
ARK_ANTHROPIC_AUTH_TOKEN
ARK_ANTHROPIC_BASE_URL
ARK_ANTHROPIC_MODEL
FEISHU_WEBHOOK_URL
```

如果飞书机器人开启了签名校验，再添加：

```text
FEISHU_WEBHOOK_SECRET
```

`ARK_ANTHROPIC_BASE_URL` 示例：

```text
https://ark.cn-beijing.volces.com/api/coding
```

配置完成后进入 `Actions -> Daily AI GitHub Report -> Run workflow` 手动运行一次验证。

## 本地验证

```bash
python3 -m unittest tests/test_daily_ai_github_report.py
python3 -m py_compile scripts/daily_ai_github_report.py tests/test_daily_ai_github_report.py
```
