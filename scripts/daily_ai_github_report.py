#!/usr/bin/env python3
"""Generate a weekly GitHub trending report and send it to Feishu."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any


USER_INTERESTS = (
    "mcp", "model-context-protocol", "mcp-server", "mcp-client",
    "ai-agent", "agent", "agentic", "ai-workflow", "agent-harness",
    "loop engineering",
    "claude code", "codex", "cursor", "kiro", "gemini-cli",
    "ai-coding", "coding-agent", "vibe-coding", "context-engineering",
    "ai-plugin", "agent-plugin", "agent-skills",
    "swift", "swiftui", "ios", "flutter",
    "macos-app", "open-source-mac-os-apps",
)

TRENDING_URL = "https://github.com/trending?since=weekly"


@dataclasses.dataclass(frozen=True)
class TrendingRepo:
    full_name: str
    url: str
    description: str
    language: str
    stars: str
    weekly_stars: str


class TrendingParser(HTMLParser):
    """Parse GitHub Trending HTML page to extract repository info."""

    def __init__(self) -> None:
        super().__init__()
        self.repos: list[TrendingRepo] = []
        self._in_article = False
        self._current: dict[str, str] = {}
        self._capture_field: str | None = None
        self._text_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "") or ""

        if tag == "article" and "Box-row" in cls:
            self._in_article = True
            self._current = {}

        if not self._in_article:
            return

        if tag == "h2" and "h3" in cls:
            self._capture_field = "name"
            self._text_buf = []

        if tag == "p" and ("col-9" in cls or "color-fg-muted" in cls):
            self._capture_field = "desc"
            self._text_buf = []

        if tag == "span" and "d-inline-block" in cls and "itemprop" in attr_dict:
            if attr_dict.get("itemprop") == "programmingLanguage":
                self._capture_field = "lang"
                self._text_buf = []

        if tag == "a" and "Link--muted" in cls and "stargazers" in (attr_dict.get("href") or ""):
            self._capture_field = "stars"
            self._text_buf = []

        if tag == "span" and "d-inline-block" in cls and "float-sm-right" in cls:
            self._capture_field = "weekly_stars"
            self._text_buf = []

    def handle_data(self, data: str) -> None:
        if self._capture_field is not None:
            self._text_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field == "name" and tag == "h2":
            text = "".join(self._text_buf).strip()
            name = "/".join(part.strip() for part in text.split("/") if part.strip())
            self._current["name"] = name
            self._capture_field = None

        elif self._capture_field == "desc" and tag == "p":
            self._current["desc"] = "".join(self._text_buf).strip()
            self._capture_field = None

        elif self._capture_field == "lang" and tag == "span":
            self._current["lang"] = "".join(self._text_buf).strip()
            self._capture_field = None

        elif self._capture_field == "stars" and tag == "a":
            self._current["stars"] = "".join(self._text_buf).strip().replace(",", "").replace(" ", "")
            self._capture_field = None

        elif self._capture_field == "weekly_stars" and tag == "span":
            self._current["weekly_stars"] = "".join(self._text_buf).strip()
            self._capture_field = None

        if tag == "article" and self._in_article:
            self._in_article = False
            name = self._current.get("name", "")
            if name:
                self.repos.append(TrendingRepo(
                    full_name=name,
                    url=f"https://github.com/{name}",
                    description=self._current.get("desc", ""),
                    language=self._current.get("lang", "Unknown"),
                    stars=self._current.get("stars", "0"),
                    weekly_stars=self._current.get("weekly_stars", ""),
                ))
            self._current = {}


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


def http_get(url: str, *, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) daily-ai-github-report",
        "Accept": "text/html",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    data = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "daily-ai-github-report",
    }
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc

    if not content:
        return {}
    return json.loads(content)


def fetch_trending_repos() -> list[TrendingRepo]:
    html = http_get(TRENDING_URL)
    parser = TrendingParser()
    parser.feed(html)
    print(f"Fetched {len(parser.repos)} repos from GitHub Trending (weekly).")
    return parser.repos


def build_anthropic_payload(model: str, repos: list[TrendingRepo], report_date: str) -> dict[str, Any]:
    interests_text = "、".join(USER_INTERESTS)
    repo_list = [dataclasses.asdict(repo) for repo in repos]
    prompt = f"""你是一个技术周报编辑。下面是本周 GitHub Trending 的全部热门项目列表。

用户是一名 iOS 开发者（Swift/Flutter），使用 Mac 电脑，日常用 AI 工具（Claude Code、Codex CLI、Kiro CLI、Cursor）进行开发，对以下方向感兴趣：
{interests_text}

请你从候选列表中筛选出 10 个最匹配用户兴趣的项目，生成一份中文「GitHub 热门项目周报」。

日期：{report_date}

输出格式要求（严格遵循）：

第一行：GitHub 热门项目周报 | {report_date}
空一行后：
📈 本周趋势总览：2-3 句话总结本周项目趋势方向。

然后逐个列出筛选出的项目，每个项目格式如下：

序号. 作者/项目名
🔗 项目链接
⭐ Stars 数 | 本周新增：周增长数 | 语言：主要语言
💡 一句话定位：用一句话说明项目做什么。
👀 看点：2-4 句话说明核心亮点、技术特色、使用方式。
🎯 适合人群：说明目标用户群体。

规则：
1. 从候选列表中精选 10 个与用户兴趣最相关的项目，优先选择与 AI 工具、MCP、Agent、编码辅助、iOS/Swift/Flutter、macOS 工具相关的项目。
2. 如果高度相关的不足 10 个，可以补充一些泛开发者工具类的优质项目。
3. 不要编造项目描述中没有提及的能力。
4. 输出为适合飞书机器人发送的纯文本，不要 Markdown 表格或代码块。
5. 项目之间空一行分隔。
6. 控制在 3500 字以内。

候选项目 JSON：
{json.dumps(repo_list, ensure_ascii=False)}
"""
    return {
        "model": model,
        "max_tokens": int(env("ANTHROPIC_MAX_TOKENS", "4096")),
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }


def build_anthropic_messages_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/messages"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/messages"
    return f"{normalized}/v1/messages"


def build_anthropic_headers(
    *,
    auth_token: str,
    api_key: str,
    api_version: str,
) -> dict[str, str]:
    headers = {"anthropic-version": api_version}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    elif api_key:
        headers["x-api-key"] = api_key
    else:
        raise RuntimeError("Missing required environment variable: ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY")
    return headers


def call_anthropic_compatible_api(repos: list[TrendingRepo], report_date: str, retries: int = 2) -> str:
    base_url = env("ANTHROPIC_BASE_URL", required=True).rstrip("/")
    auth_token = env("ANTHROPIC_AUTH_TOKEN")
    api_key = env("ANTHROPIC_API_KEY")
    model = env("ANTHROPIC_MODEL", required=True)
    api_version = env("ANTHROPIC_VERSION", "2023-06-01")
    url = build_anthropic_messages_url(base_url)
    payload = build_anthropic_payload(model, repos, report_date)
    headers = build_anthropic_headers(auth_token=auth_token, api_key=api_key, api_version=api_version)
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(retries):
        try:
            result = http_json(url, method="POST", headers=headers, body=payload, timeout=180)
            parts = []
            for block in result.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            text = "\n".join(parts).strip()
            if not text:
                raise RuntimeError(f"Anthropic compatible API returned empty text: {result}")
            return text
        except Exception as exc:
            last_exc = exc
            print(f"Anthropic API attempt {attempt + 1}/{retries} failed: {exc}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(5)
    raise last_exc


def build_feishu_payload(
    text: str,
    *,
    secret: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if secret:
        timestamp = timestamp or str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(
            string_to_sign.encode("utf-8"),
            b"",
            digestmod=hashlib.sha256,
        ).digest()
        payload["timestamp"] = timestamp
        payload["sign"] = base64.b64encode(digest).decode("utf-8")
    return payload


def send_feishu_message(text: str) -> None:
    webhook_url = env("FEISHU_WEBHOOK_URL", required=True)
    secret = env("FEISHU_WEBHOOK_SECRET", "")
    payload = build_feishu_payload(text, secret=secret)
    result = http_json(webhook_url, method="POST", body=payload)
    code = result.get("code", result.get("StatusCode", 0))
    if code not in (0, "0"):
        raise RuntimeError(f"Feishu webhook failed: {result}")


def build_fallback_report(repos: list[TrendingRepo], report_date: str) -> str:
    lines = [f"GitHub 热门项目周报｜{report_date}", "", "模型摘要失败，以下是本周 Trending 项目清单："]
    for index, repo in enumerate(repos[:20], 1):
        lines.extend([
            "",
            f"{index}. {repo.full_name}",
            f"⭐ {repo.stars} | 本周：{repo.weekly_stars} | {repo.language}",
            repo.url,
            repo.description or "暂无描述",
        ])
    return "\n".join(lines)


def main() -> int:
    report_date = datetime.now(timezone(timedelta(hours=8))).date().isoformat()

    repos = fetch_trending_repos()
    if not repos:
        send_feishu_message(f"GitHub 热门项目周报｜{report_date}\n\n本周未能获取 Trending 数据。")
        print("No repositories found from GitHub Trending; sent empty-result notice.")
        return 0

    try:
        report = call_anthropic_compatible_api(repos, report_date)
    except Exception as exc:
        print(f"AI summary failed, sending fallback report: {exc}", file=sys.stderr)
        report = build_fallback_report(repos, report_date)

    send_feishu_message(report)
    print(f"Sent weekly report based on {len(repos)} trending repositories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
