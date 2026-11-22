"""I contratti delle porte girano sugli adattatori finti: prova che i fake sono fedeli alla porta."""
from datetime import datetime, timezone

import pytest

from ports import MarketData, NewsFeed
from tests.contracts.market_data_contract import check_market_data
from tests.contracts.news_contract import check_news_feed
from tests.fakes import FakeMarketData, FakeNews

NOW = datetime(2026, 3, 2, 12, 7, tzinfo=timezone.utc)  # a metà della candela M15 12:00–12:15


def test_fake_market_data_honours_contract():
    check_market_data(FakeMarketData(now=NOW, tf_minutes=15), "EURUSD", "M15", 15, NOW)


def test_fake_market_data_is_a_market_data():
    assert isinstance(FakeMarketData(now=NOW, tf_minutes=15), MarketData)


def test_contract_rejects_forming_candle():
    forming = FakeMarketData(now=NOW, tf_minutes=15, include_forming=True)
    with pytest.raises(AssertionError, match="formazione"):
        check_market_data(forming, "EURUSD", "M15", 15, NOW)


def test_fake_news_honours_contract():
    check_news_feed(FakeNews(now=NOW), "EURUSD", NOW)


def test_fake_news_is_a_news_feed():
    assert isinstance(FakeNews(now=NOW), NewsFeed)
