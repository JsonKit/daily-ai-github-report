import json
import unittest
from datetime import date

from scripts.daily_ai_github_report import (
    AI_KEYWORDS,
    EXCLUDED_SEARCH_TERMS,
    GitHubRepo,
    build_anthropic_headers,
    build_anthropic_payload,
    build_anthropic_messages_url,
    build_feishu_payload,
    build_github_search_query,
    extract_json_object,
    parse_github_repo,
    rank_repositories,
)


class DailyAiGitHubReportTests(unittest.TestCase):
    def test_search_keywords_focus_on_ready_to_use_ai_tools(self):
        self.assertIn("mcp", AI_KEYWORDS)
        self.assertIn("claude-code", AI_KEYWORDS)
        self.assertIn("codex", AI_KEYWORDS)
        self.assertIn("plugin", AI_KEYWORDS)
        self.assertIn("skill", AI_KEYWORDS)
        self.assertNotIn("llm", AI_KEYWORDS)
        self.assertNotIn("machine-learning", AI_KEYWORDS)
        self.assertNotIn("deep-learning", AI_KEYWORDS)
        self.assertNotIn("generative-ai", AI_KEYWORDS)

    def test_build_github_search_query_excludes_learning_content(self):
        query = build_github_search_query("mcp", "2026-06-01")

        self.assertIn("mcp", query)
        self.assertIn("created:>=2026-06-01", query)
        self.assertIn("stars:>20", query)
        for excluded in EXCLUDED_SEARCH_TERMS:
            self.assertIn(f"-{excluded}", query)

    def test_parse_github_repo_normalizes_api_response(self):
        payload = {
            "full_name": "owner/project",
            "html_url": "https://github.com/owner/project",
            "description": "AI coding assistant",
            "stargazers_count": 1200,
            "language": "Python",
            "created_at": "2026-06-01T01:02:03Z",
            "updated_at": "2026-06-08T04:05:06Z",
            "pushed_at": "2026-06-08T04:05:06Z",
            "topics": ["ai", "agent"],
        }

        repo = parse_github_repo(payload)

        self.assertEqual(repo.full_name, "owner/project")
        self.assertEqual(repo.stars, 1200)
        self.assertEqual(repo.topics, ["ai", "agent"])

    def test_rank_repositories_deduplicates_and_orders_by_score(self):
        repos = [
            GitHubRepo(
                full_name="a/old",
                url="https://github.com/a/old",
                description="",
                stars=1000,
                language="Python",
                created_at="2026-05-01T00:00:00Z",
                updated_at="2026-06-01T00:00:00Z",
                pushed_at="2026-06-01T00:00:00Z",
                topics=[],
            ),
            GitHubRepo(
                full_name="b/new",
                url="https://github.com/b/new",
                description="",
                stars=120,
                language="TypeScript",
                created_at="2026-06-08T00:00:00Z",
                updated_at="2026-06-08T00:00:00Z",
                pushed_at="2026-06-08T00:00:00Z",
                topics=[],
            ),
            GitHubRepo(
                full_name="b/new",
                url="https://github.com/b/new",
                description="duplicate",
                stars=120,
                language="TypeScript",
                created_at="2026-06-08T00:00:00Z",
                updated_at="2026-06-08T00:00:00Z",
                pushed_at="2026-06-08T00:00:00Z",
                topics=[],
            ),
        ]

        ranked = rank_repositories(repos, today=date(2026, 6, 9), limit=2)

        self.assertEqual([repo.full_name for repo in ranked], ["b/new", "a/old"])

    def test_extract_json_object_handles_wrapped_model_text(self):
        text = "下面是结果：\n```json\n{\"items\": [1], \"summary\": \"ok\"}\n```"

        result = extract_json_object(text)

        self.assertEqual(result, {"items": [1], "summary": "ok"})

    def test_build_anthropic_payload_uses_messages_api_shape(self):
        repos = [
            GitHubRepo(
                full_name="owner/project",
                url="https://github.com/owner/project",
                description="AI coding assistant",
                stars=1200,
                language="Python",
                created_at="2026-06-01T01:02:03Z",
                updated_at="2026-06-08T04:05:06Z",
                pushed_at="2026-06-08T04:05:06Z",
                topics=["ai"],
                readme_excerpt="README",
            )
        ]

        payload = build_anthropic_payload("claude-test", repos, "2026-06-09")

        self.assertEqual(payload["model"], "claude-test")
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertIn("GitHub AI 热门项目日报", payload["messages"][0]["content"])

    def test_build_anthropic_messages_url_appends_v1_messages(self):
        self.assertEqual(
            build_anthropic_messages_url("https://ark.cn-beijing.volces.com/api/coding"),
            "https://ark.cn-beijing.volces.com/api/coding/v1/messages",
        )
        self.assertEqual(
            build_anthropic_messages_url("https://api.anthropic.com/v1"),
            "https://api.anthropic.com/v1/messages",
        )

    def test_build_anthropic_headers_prefers_auth_token(self):
        headers = build_anthropic_headers(
            auth_token="ark-token",
            api_key="api-key",
            api_version="2023-06-01",
        )

        self.assertEqual(headers["Authorization"], "Bearer ark-token")
        self.assertNotIn("x-api-key", headers)

    def test_build_feishu_payload_supports_signed_webhook(self):
        payload = build_feishu_payload("hello", secret="secret", timestamp="123")

        self.assertEqual(payload["msg_type"], "text")
        self.assertEqual(payload["timestamp"], "123")
        self.assertIn("sign", payload)
        self.assertEqual(payload["sign"], "/1VVdZH3KitTHu9FiYl+TZ0EGq/rppGGi7XFsB5aJSA=")
        self.assertEqual(json.loads(json.dumps(payload))["content"]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
