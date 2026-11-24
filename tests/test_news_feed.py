"""Eseguire con: .venv\\Scripts\\python.exe -m unittest discover tests"""
import unittest
from unittest import mock

from core.news_feed import YahooNewsFeed

RSS = b"""<rss><channel>
<item><title>Old</title><pubDate>Mon, 12 Oct 2026 10:00:00 +0000</pubDate><description>&lt;p&gt;a&lt;/p&gt;</description></item>
<item><title>New</title><pubDate>Wed, 14 Oct 2026 10:00:00 +0000</pubDate><description>b</description></item>
</channel></rss>"""


class YahooNewsFeedTest(unittest.TestCase):
    def test_ticker_mapping(self):
        self.assertEqual(YahooNewsFeed._ticker("EURUSD"), "EURUSD=X")
        self.assertEqual(YahooNewsFeed._ticker("USDJPY"), "JPY=X")

    def test_parses_sorts_newest_first_and_strips_html(self):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = RSS
        with mock.patch("urllib.request.urlopen", return_value=resp):
            items = YahooNewsFeed().get_latest_news("EURUSD", limit=2)
        self.assertEqual([i["headline"] for i in items], ["New", "Old"])
        self.assertEqual(items[1]["summary"], "a")

    def test_network_failure_returns_empty_not_fake_news(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertEqual(YahooNewsFeed().get_latest_news("EURUSD"), [])


if __name__ == "__main__":
    unittest.main()
