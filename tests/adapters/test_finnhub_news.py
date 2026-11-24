"""P3.18: notizie forex da Finnhub (uso privato, T-008). Opener HTTP e orologio iniettati: nessuna rete.
published_at dal campo UNIX `datetime` in UTC, fetched_at dall'orologio, errori di rete → lista vuota,
chiave mai nei log né nell'URL."""
import io
import json
import logging
import urllib.error
from datetime import datetime, timezone

from pydantic import SecretStr

from adapters.finnhub_news import FinnhubNews
from ports import NewsFeed
from tests.contracts.news_contract import check_news_feed

KEY = "fh-test-key-0123456789"
NOW = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
ITEMS = [
    {"category": "forex", "datetime": 1795424400, "headline": "BCE lascia i tassi invariati", "id": 1,
     "source": "Reuters", "summary": "…", "url": "https://example.invalid/1"},
    {"category": "forex", "datetime": 1795428000, "headline": "Dollaro in calo dopo i dati USA", "id": 2,
     "source": "", "summary": "…", "url": "https://example.invalid/2"},
]


class FakeOpener:
    def __init__(self, payload=ITEMS, error: Exception | None = None):
        self.payload, self.error, self.requests = payload, error, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.payload).encode())


def _feed(opener):
    return FinnhubNews(SecretStr(KEY), opener=opener, clock=lambda: NOW)


def test_finnhub_honours_contract():
    check_news_feed(_feed(FakeOpener()), "EURUSD", NOW)
    assert isinstance(_feed(FakeOpener()), NewsFeed)


def test_maps_unix_datetime_to_utc():
    items = _feed(FakeOpener()).latest("EURUSD", 10)
    assert items[-1].published_at == datetime.fromtimestamp(1795424400, tz=timezone.utc)
    assert items[0].published_at.tzinfo == timezone.utc


def test_newest_first_and_limit():
    items = _feed(FakeOpener()).latest("EURUSD", 1)
    assert [n.headline for n in items] == ["Dollaro in calo dopo i dati USA"]


def test_fetched_at_from_clock():
    assert all(n.fetched_at == NOW for n in _feed(FakeOpener()).latest("EURUSD", 10))


def test_missing_source_falls_back_to_finnhub():
    assert _feed(FakeOpener()).latest("EURUSD", 10)[0].source == "finnhub"


def test_malformed_items_are_skipped():
    bad = [{"headline": "senza data"}, {"datetime": "x", "headline": "data rotta"}, {"datetime": 1795424400, "headline": "  "},
           ITEMS[0]]
    assert [n.headline for n in _feed(FakeOpener(payload=bad)).latest("EURUSD", 10)] == [ITEMS[0]["headline"]]


def test_network_error_returns_empty():
    assert _feed(FakeOpener(error=urllib.error.URLError("timeout"))).latest("EURUSD", 10) == []
    assert _feed(FakeOpener(error=TimeoutError())).latest("EURUSD", 10) == []
    assert _feed(FakeOpener(payload={"error": "limite superato"})).latest("EURUSD", 10) == []


def test_key_sent_in_header_not_in_url():
    opener = FakeOpener()
    _feed(opener).latest("EURUSD", 10)
    req = opener.requests[0]
    assert KEY not in req.full_url and req.get_header("X-finnhub-token") == KEY
    assert "category=forex" in req.full_url and req.full_url.startswith("https://")


def test_key_redacted_in_logs(caplog):
    err = urllib.error.HTTPError("https://finnhub.io/api/v1/news", 401, f"token {KEY} non valido", {}, None)
    with caplog.at_level(logging.DEBUG):
        _feed(FakeOpener(error=err)).latest("EURUSD", 10)
    assert caplog.records and KEY not in caplog.text and "***" in caplog.text
    assert KEY not in repr(_feed(FakeOpener()).__dict__)
