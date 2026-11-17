"""robots.txt decisions. No network."""

from collector.http_policy import COLLECTOR_UA, HostPolicy, RobotsDenied, _crawl_delay
from urllib.robotparser import RobotFileParser


class _Resp:
    def __init__(self, status: int, text: str = "") -> None:
        self.status_code = status
        self.text = text


def _policy(body: str) -> HostPolicy:
    def get(_url, _headers):
        return _Resp(200, body)

    return HostPolicy(session_get=get, gap_s=0)


def test_crawl_delay_for_star_agent():
    body = "User-agent: *\nCrawl-delay: 10\nDisallow:\n"
    assert _crawl_delay(body) == 10


def test_disallow_search_and_pdf_and_year():
    body = """
User-agent: *
Disallow: /search
Disallow: *.pdf
Disallow: /what-s-happening/news/2020/
Disallow: /wp-json/
Allow: /
"""
    policy = _policy(body)
    ok = "https://example.gov/news/child-case"
    policy.acquire(ok)
    for blocked in (
        "https://example.gov/search?q=child",
        "https://example.gov/files/report.pdf",
        "https://example.gov/what-s-happening/news/2020/may/story",
        "https://example.gov/wp-json/wp/v2/posts",
    ):
        try:
            policy.acquire(blocked)
        except RobotsDenied:
            continue
        raise AssertionError(blocked)


def test_missing_robots_allows_fetch():
    def get(_url, _headers):
        return _Resp(404, "")

    policy = HostPolicy(session_get=get, gap_s=0)
    policy.acquire("https://example.gov/news/one")


def test_user_agent_is_not_a_browser():
    assert "Mozilla" not in COLLECTOR_UA
    assert "CaseLinkerCollector" in COLLECTOR_UA
    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /search"])
    assert parser.can_fetch(COLLECTOR_UA, "https://example.gov/search") is False
    assert parser.can_fetch(COLLECTOR_UA, "https://example.gov/news/one") is True
