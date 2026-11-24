"""R3 / D-015: le notizie live si scaricano dopo la chiusura (fetched_at > chiusura) e la regola anti-futuro
le scartava tutte. La cache restituisce solo ciò che era già noto prima di questa lettura, con il suo
fetched_at originale: notizie con una candela di ritardo, regola anti-futuro intatta."""
from datetime import datetime, timedelta, timezone

from adapters.news_cache import CachedNews
from domain.news import NewsItem, visible_news

T0 = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
DELAY = timedelta(seconds=10)  # il ciclo parte dopo la chiusura, come lo scheduler


class LiveFeed:
    """Come Finnhub: fetched_at = adesso, quindi sempre dopo la chiusura della candela."""

    def __init__(self):
        self.now = T0 + DELAY

    def latest(self, symbol, limit):
        return [NewsItem(f"titolo {self.now:%H%M}", "x", self.now - timedelta(minutes=5), self.now)]


def test_without_cache_live_news_is_never_visible():
    feed = LiveFeed()
    assert visible_news(feed.latest("EURUSD", 10), T0) == []  # il difetto trovato in review


def test_cache_serves_news_known_before_the_close():
    feed = LiveFeed()
    cache = CachedNews(feed)
    assert cache.latest("EURUSD", 10) == []  # primo ciclo: niente di già noto

    feed.now += timedelta(minutes=15)  # ciclo della candela successiva
    items = cache.latest("EURUSD", 10)
    assert [n.headline for n in visible_news(items, T0 + timedelta(minutes=15))] == ["titolo 1000"]
    assert items[0].fetched_at == T0 + DELAY  # fetched_at originale, mai riscritto


def test_same_item_keeps_first_fetched_at():
    fixed = NewsItem("BCE invariata", "x", T0 - timedelta(hours=1), T0 + DELAY)

    class Repeating:
        def __init__(self):
            self.calls = 0

        def latest(self, symbol, limit):
            self.calls += 1
            return [NewsItem(fixed.headline, "x", fixed.published_at, T0 + DELAY * self.calls)]

    cache = CachedNews(Repeating())
    for _ in range(3):
        items = cache.latest("EURUSD", 10)
    assert [(n.headline, n.fetched_at) for n in items] == [("BCE invariata", T0 + DELAY)]


def test_cache_survives_restart(tmp_path):
    path = tmp_path / "news_cache.json"
    feed = LiveFeed()
    CachedNews(feed, path).latest("EURUSD", 10)
    feed.now += timedelta(minutes=15)
    items = CachedNews(feed, path).latest("EURUSD", 10)  # processo nuovo, come python main.py --once
    assert [n.headline for n in items] == ["titolo 1000"] and items[0].fetched_at == T0 + DELAY


def test_corrupt_cache_file_starts_empty(tmp_path, caplog):
    path = tmp_path / "news_cache.json"
    path.write_text("{non json", encoding="utf-8")
    assert CachedNews(LiveFeed(), path).latest("EURUSD", 10) == []
    assert "cache delle notizie" in caplog.text


def test_cache_is_per_symbol_and_respects_limit():
    feed = LiveFeed()
    cache = CachedNews(feed)
    for _ in range(4):
        cache.latest("EURUSD", 2)
        feed.now += timedelta(minutes=15)
    assert len(cache.latest("EURUSD", 2)) == 2 and cache.latest("GBPUSD", 2) == []
