"""Contratto della porta NewsFeed: lo stesso controllo gira sul fake e (P3.18) sull'adattatore Finnhub."""
from datetime import datetime

from ports import NewsItem


def check_news_feed(adapter, symbol: str, now: datetime, limit: int = 10):
    items = adapter.latest(symbol, limit)

    assert isinstance(items, list) and len(items) <= limit
    for n in items:
        assert isinstance(n, NewsItem)
        assert n.published_at.tzinfo is not None and n.fetched_at.tzinfo is not None
        assert n.fetched_at <= now, "fetched_at nel futuro"
        assert n.headline.strip(), "titolo vuoto"
