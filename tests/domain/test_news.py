"""P3.11: regola anti-futuro sulle notizie. Una notizia entra nel ciclo di una candela solo se
era già stata scaricata (fetched_at) e pubblicata (published_at) entro la chiusura."""
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.news import visible_news
from ports import NewsItem

CLOSE = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)


def _item(published_offset_min, fetched_offset_min):
    return NewsItem(
        headline="h", source="s",
        published_at=CLOSE + timedelta(minutes=published_offset_min),
        fetched_at=CLOSE + timedelta(minutes=fetched_offset_min),
    )


def test_news_fetched_before_close_is_visible():
    assert visible_news([_item(-60, -30)], CLOSE) == [_item(-60, -30)]


def test_news_fetched_exactly_at_close_is_visible():
    assert len(visible_news([_item(-5, 0)], CLOSE)) == 1


def test_news_fetched_after_close_is_hidden():
    # pubblicata prima, ma scaricata dopo la chiusura: nel backtest non l'avremmo avuta
    assert visible_news([_item(-60, 1)], CLOSE) == []


def test_news_published_after_close_is_hidden():
    # orologio della fonte sfasato: published_at nel futuro rispetto alla chiusura
    assert visible_news([_item(5, -1)], CLOSE) == []


def test_naive_candle_close_raises():
    with pytest.raises(ValueError):
        visible_news([], CLOSE.replace(tzinfo=None))


def test_news_item_requires_aware_timestamps():
    with pytest.raises(ValueError):
        NewsItem("h", "s", CLOSE.replace(tzinfo=None), CLOSE)


offsets = st.integers(min_value=-600, max_value=600)


@given(st.lists(st.tuples(offsets, offsets), max_size=20))
def test_visible_news_never_passes_fetched_after_close(pairs):
    items = [_item(p, f) for p, f in pairs]
    for n in visible_news(items, CLOSE):
        assert n.fetched_at <= CLOSE and n.published_at <= CLOSE
