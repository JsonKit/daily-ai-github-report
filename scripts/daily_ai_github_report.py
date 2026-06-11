#!/usr/bin/env python3
"""Generate a daily GitHub AI project report and send it to Feishu."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any


GITHUB_API = "https://api.github.com"
AI_KEYWORDS = (
    "mcp",
    "model-context-protocol",
    "ai-agent",
    "agent",
    "claude-code",
    "codex",
    "plugin",
    "plugins",
    "skill",
    "skills",
    "automation",
    "developer-tools",
    "cli",
    "vscode-extension",
    "cursor",
)

@dataclasses.dataclass(frozen=True)
class GitHubRepo:
    full_name: str
    url: str
    description: str
    stars: int
    language: str
    created_at: str
    updated_at: str
    pushed_at: str
    topics: list[str]
    readme_excerpt: str = ""


@dataclasses.dataclass(frozen=True)
class GitHubSearchRound:
    name: str
    created_days: int | None = None
    pushed_days: int | None = None
    min_stars: int = 20


SEARCH_ROUNDS = (
    GitHubSearchRound(name="recent-created", created_days=14, min_stars=20),
    GitHubSearchRound(name="wider-created", created_days=30, min_stars=10),
    GitHubSearchRound(name="recently-pushed", pushed_days=14, min_stars=50),
)


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


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

    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc

    if not content:
        return {}
    return json.loads(content)


def parse_github_repo(item: dict[str, Any]) -> GitHubRepo:
    return GitHubRepo(
        full_name=str(item.get("full_name") or ""),
        url=str(item.get("html_url") or ""),
        description=str(item.get("description") or ""),
        stars=int(item.get("stargazers_count") or 0),
        language=str(item.get("language") or "Unknown"),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
        pushed_at=str(item.get("pushed_at") or ""),
        topics=list(item.get("topics") or []),
    )


def parse_date(value: str) -> date:
    if not value:
        return date(1970, 1, 1)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def repo_score(repo: GitHubRepo, today: date) -> float:
    created_days = max((today - parse_date(repo.created_at)).days, 0)
    pushed_days = max((today - parse_date(repo.pushed_at)).days, 0)
    recency_bonus = max(0, 30 - created_days) * 12 + max(0, 14 - pushed_days) * 4
    return math.log10(repo.stars + 1) * 100 + recency_bonus


def rank_repositories(
    repos: list[GitHubRepo],
    *,
    today: date | None = None,
    limit: int = 8,
) -> list[GitHubRepo]:
    today = today or datetime.now(timezone.utc).date()
    deduped: dict[str, GitHubRepo] = {}
    for repo in repos:
        if repo.full_name and repo.full_name not in deduped:
            deduped[repo.full_name] = repo
    return sorted(
        deduped.values(),
        key=lambda repo: repo_score(repo, today),
        reverse=True,
    )[:limit]


def build_github_search_query(
    keyword: str,
    *,
    created_since: str | None = None,
    pushed_since: str | None = None,
    min_stars: int = 20,
) -> str:
    date_filter = ""
    if created_since:
        date_filter = f"created:>={created_since}"
    elif pushed_since:
        date_filter = f"pushed:>={pushed_since}"
    else:
        raise ValueError("created_since or pushed_since is required")
    return f"{keyword} {date_filter} stars:>{min_stars}"


def search_github_repositories(token: str, per_keyword: int = 6) -> list[GitHubRepo]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for search_round in SEARCH_ROUNDS:
        repos: list[GitHubRepo] = []
        created_since = (
            (datetime.now(timezone.utc) - timedelta(days=search_round.created_days)).date().isoformat()
            if search_round.created_days is not None
            else None
        )
        pushed_since = (
            (datetime.now(timezone.utc) - timedelta(days=search_round.pushed_days)).date().isoformat()
            if search_round.pushed_days is not None
            else None
        )
        for keyword in AI_KEYWORDS:
            query = build_github_search_query(
                keyword,
                created_since=created_since,
                pushed_since=pushed_since,
                min_stars=search_round.min_stars,
            )
            params = urllib.parse.urlencode(
                {
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": str(per_keyword),
                }
            )
            result = http_json(f"{GITHUB_API}/search/repositories?{params}", headers=headers)
            items = result.get("items", [])
            print(f"GitHub search round={search_round.name} keyword={keyword} count={len(items)}")
            repos.extend(parse_github_repo(item) for item in items)
            time.sleep(0.8)
        if repos:
            print(f"GitHub search round={search_round.name} selected with {len(repos)} raw repositories.")
            return repos
    return []


def fetch_readme_excerpt(repo: GitHubRepo, token: str, max_chars: int = 4500) -> str:
    headers = {"Accept": "application/vnd.github.raw"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{GITHUB_API}/repos/{repo.full_name}/readme"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    return text[:max_chars]


def enrich_with_readmes(repos: list[GitHubRepo], token: str) -> list[GitHubRepo]:
    enriched = []
    for repo in repos:
        enriched.append(dataclasses.replace(repo, readme_excerpt=fetch_readme_excerpt(repo, token)))
        time.sleep(0.5)
    return enriched


def build_anthropic_payload(model: str, repos: list[GitHubRepo], report_date: str) -> dict[str, Any]:
    repo_payload = [dataclasses.asdict(repo) for repo in repos]
    prompt = f"""请生成一份中文「GitHub AI 热门项目日报」。

日期：{report_date}

要求：
1. 先给出 2-3 句总览，说明今天项目趋势。
2. 挑选全部候选项目逐个总结，每个项目包含：项目名、链接、Stars、语言、一句话定位、看点、适合人群。
3. 不要编造 README 中没有依据的能力。
4. 输出为适合飞书机器人发送的纯文本，不要 Markdown 表格。
5. 控制在 3500 字以内。

候选项目 JSON：
{json.dumps(repo_payload, ensure_ascii=False)}
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


def call_anthropic_compatible_api(repos: list[GitHubRepo], report_date: str) -> str:
    base_url = env("ANTHROPIC_BASE_URL", required=True).rstrip("/")
    auth_token = env("ANTHROPIC_AUTH_TOKEN")
    api_key = env("ANTHROPIC_API_KEY")
    model = env("ANTHROPIC_MODEL", required=True)
    api_version = env("ANTHROPIC_VERSION", "2023-06-01")
    url = build_anthropic_messages_url(base_url)
    payload = build_anthropic_payload(model, repos, report_date)
    result = http_json(
        url,
        method="POST",
        headers=build_anthropic_headers(
            auth_token=auth_token,
            api_key=api_key,
            api_version=api_version,
        ),
        body=payload,
        timeout=90,
    )
    parts = []
    for block in result.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    text = "\n".join(parts).strip()
    if not text:
        raise RuntimeError(f"Anthropic compatible API returned empty text: {result}")
    return text


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in text")
    return json.loads(stripped[start : end + 1])


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


def build_fallback_report(repos: list[GitHubRepo], report_date: str) -> str:
    lines = [f"GitHub AI 热门项目日报｜{report_date}", "", "模型摘要失败，以下是候选项目清单："]
    for index, repo in enumerate(repos, 1):
        lines.extend(
            [
                "",
                f"{index}. {repo.full_name}",
                f"Stars: {repo.stars} | Language: {repo.language}",
                repo.url,
                repo.description or "暂无描述",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    github_token = env("GH_TOKEN", env("GITHUB_TOKEN", ""))
    report_date = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    limit = int(env("REPORT_REPO_LIMIT", "8"))

    repos = search_github_repositories(github_token)
    ranked = rank_repositories(repos, limit=limit)
    if not ranked:
        send_feishu_message(f"GitHub AI 热门项目日报｜{report_date}\n\n今日未发现符合条件的 AI 应用工具项目。")
        print("No repositories found from GitHub search; sent empty-result notice.")
        return 0

    enriched = enrich_with_readmes(ranked, github_token)
    try:
        report = call_anthropic_compatible_api(enriched, report_date)
    except Exception as exc:
        print(f"AI summary failed, sending fallback report: {exc}", file=sys.stderr)
        report = build_fallback_report(enriched, report_date)

    send_feishu_message(report)
    print(f"Sent GitHub AI report with {len(enriched)} repositories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
