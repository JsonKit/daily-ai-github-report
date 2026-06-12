import json
import unittest
from unittest.mock import patch

from scripts.daily_ai_github_report import (
    USER_INTERESTS,
    TRENDING_URL,
    TrendingParser,
    TrendingRepo,
    build_anthropic_headers,
    build_anthropic_messages_url,
    build_anthropic_payload,
    build_feishu_payload,
    main,
)


class WeeklyGitHubReportTests(unittest.TestCase):
    def test_user_interests_contains_core_topics(self):
        self.assertIn("mcp", USER_INTERESTS)
        self.assertIn("claude code", USER_INTERESTS)
        self.assertIn("codex", USER_INTERESTS)
        self.assertIn("swift", USER_INTERESTS)
        self.assertIn("flutter", USER_INTERESTS)
        self.assertNotIn("llm", USER_INTERESTS)
        self.assertNotIn("machine-learning", USER_INTERESTS)

    def test_trending_url_is_weekly(self):
        self.assertIn("since=weekly", TRENDING_URL)

    def test_trending_parser_extracts_repos(self):
        html = """
        <article class="Box-row">
          <h2 class="h3 lh-condensed">
            <a href="/owner/project">owner / project</a>
          </h2>
          <p class="col-9 color-fg-muted my-1 pr-4">A cool project</p>
          <span class="d-inline-block ml-0 mr-3" itemprop="programmingLanguage">Python</span>
          <a class="Link--muted d-inline-block mr-3" href="/owner/project/stargazers">1,234</a>
          <span class="d-inline-block float-sm-right">456 stars this week</span>
        </article>
        """
        parser = TrendingParser()
        parser.feed(html)

        self.assertEqual(len(parser.repos), 1)
        repo = parser.repos[0]
        self.assertEqual(repo.full_name, "owner/project")
        self.assertEqual(repo.url, "https://github.com/owner/project")
        self.assertEqual(repo.description, "A cool project")
        self.assertEqual(repo.language, "Python")
        self.assertEqual(repo.stars, "1234")
        self.assertEqual(repo.weekly_stars, "456 stars this week")

    def test_build_anthropic_payload_includes_interests(self):
        repos = [TrendingRepo(
            full_name="owner/proj",
            url="https://github.com/owner/proj",
            description="test",
            language="Python",
            stars="100",
            weekly_stars="50 stars this week",
        )]
        payload = build_anthropic_payload("test-model", repos, "2026-06-12")

        self.assertEqual(payload["model"], "test-model")
        content = payload["messages"][0]["content"]
        self.assertIn("GitHub 热门项目周报", content)
        self.assertIn("mcp", content)
        self.assertIn("swift", content)

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

    def test_main_sends_notice_when_no_repos_found(self):
        sent_messages = []

        with (
            patch("scripts.daily_ai_github_report.fetch_trending_repos", return_value=[]),
            patch("scripts.daily_ai_github_report.send_feishu_message", side_effect=sent_messages.append),
        ):
            result = main()

        self.assertEqual(result, 0)
        self.assertEqual(len(sent_messages), 1)
        self.assertIn("本周未能获取 Trending 数据", sent_messages[0])


if __name__ == "__main__":
    unittest.main()
