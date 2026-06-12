# GitHub 热门项目周报

每周一 09:00（北京时间）通过 GitHub Actions 抓取 GitHub Trending（weekly）热门项目，调用 AI 根据用户兴趣偏好筛选并生成中文摘要，然后发送到飞书群机器人。

用户兴趣方向：MCP、Agent、AI 编码工具（Claude Code / Codex / Cursor / Kiro）、Agent Skills/Plugin、Swift/iOS、Flutter、macOS 开源工具等。

## 工作流程

1. 抓取 `github.com/trending?since=weekly` 获取本周全语言热门项目
2. 将完整列表 + 用户兴趣关键词传给 AI
3. AI 筛选 10 个最匹配的项目并生成结构化周报
4. 推送到飞书群

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

配置完成后进入 `Actions -> Weekly AI GitHub Report -> Run workflow` 手动运行一次验证。

## 本地验证

```bash
python3 -m unittest tests/test_daily_ai_github_report.py
python3 -m py_compile scripts/daily_ai_github_report.py
```
