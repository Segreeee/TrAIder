"""P3.25: run_once, parte 1. Dati → candidato → analisti LLM → archivio, su porte finte.
Idempotenza per candela, macro solo con notizie visibili, LLM giù = caratteristiche mancanti."""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.config import Settings
from app.run_once import Ports, run_once
from ports import NewsItem
from tests.fakes import FakeLlm, FakeNews, FakeStore

START = datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
VIEW_BUY = '{"direzione": 1, "forza": 2, "orizzonte": "intraday", "motivazioni": ["trend"]}'


def _bars(closes, freq_min, start):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    return pd.DataFrame({
        "timestamp": pd.date_range(start, periods=len(closes), freq=f"{freq_min}min", tz="UTC"),
        "open": opens, "high": np.maximum(opens, closes) + 0.0003, "low": np.minimum(opens, closes) - 0.0003,
        "close": closes, "volume": 100, "spread": 8,
    })


def _trend(n, step, start):
    return start + step * np.arange(n) + 0.0002 * np.sin(np.arange(n))


class TableMarket:
    """Dati di mercato fissi: un trend al rialzo su entrambi i timeframe (genera un BUY) oppure discordante."""

    def __init__(self, h1_step=0.0004, fail=False):
        self.m15 = _bars(_trend(200, 0.0001, 1.10), 15, START)
        self.h1 = _bars(_trend(120, h1_step, 1.09 if h1_step > 0 else 1.12), 60, START - timedelta(hours=70))
        self.fail = fail

    def closed_bars(self, symbol, timeframe, count):
        if self.fail:
            raise RuntimeError("terminale MT5 non raggiungibile")
        return (self.m15 if timeframe == "M15" else self.h1).tail(count).reset_index(drop=True)


CLOSE = START + timedelta(minutes=15 * 200)  # chiusura dell'ultima barra M15


def _ports(market=None, news_items=(), tech=None, macro=None):
    return Ports(market=market or TableMarket(), news=FakeNews(CLOSE, items=list(news_items)),
                 technical=tech or FakeLlm([VIEW_BUY] * 5), macro=macro or FakeLlm([VIEW_BUY] * 5),
                 store=FakeStore())


def _cfg():
    return Settings(_env_file=None)


def test_candidate_runs_technical_and_records_everything():
    ports = _ports()
    report = run_once("EURUSD", CLOSE, ports, _cfg(), code_version="abc123")
    assert report.status == "done" and report.candidate is not None
    assert report.features["tecnico"] == 2.0 and report.features["macro"] is None
    assert [role for _, role, _ in ports.store.llm_calls] == ["tecnico"]
    finished = ports.store.finished[1]
    assert finished["status"] == "done" and finished["code_version"] == "abc123"
    assert finished["config_hash"] == _cfg().config_hash()
    snapshot = json.loads(finished["input_json"])
    assert snapshot["candle_close_utc"] == CLOSE.isoformat() and snapshot["news"] == []
    assert len(snapshot["bars_m15"]) > 0 and snapshot["htf_trend"] == "rialzista"


def test_second_call_same_candle_does_nothing():
    ports = _ports()
    run_once("EURUSD", CLOSE, ports, _cfg())
    calls = len(ports.technical.calls)
    report = run_once("EURUSD", CLOSE, ports, _cfg())
    assert report.status == "skipped"
    assert len(ports.technical.calls) == calls and len(ports.store.cycles) == 1


def test_no_candidate_records_cycle_with_NO_CANDIDATE():
    ports = _ports(market=TableMarket(h1_step=-0.0004))
    report = run_once("EURUSD", CLOSE, ports, _cfg())
    assert report.status == "done" and report.candidate is None and report.hold_reason == "NO_CANDIDATE"
    assert ports.store.finished[1]["status"] == "done"


def test_llm_called_only_with_candidate():
    ports = _ports(market=TableMarket(h1_step=-0.0004))
    run_once("EURUSD", CLOSE, ports, _cfg())
    assert ports.technical.calls == [] and ports.macro.calls == []


def test_macro_only_with_visible_news():
    # porting di ActiveAnalystsTest: senza notizie visibili il macro è escluso
    late = NewsItem("Notizia scaricata dopo la chiusura", "x", CLOSE - timedelta(hours=1), CLOSE + timedelta(minutes=5))
    ports = _ports(news_items=[late])
    run_once("EURUSD", CLOSE, ports, _cfg())
    assert ports.macro.calls == []

    visible = NewsItem("BCE invariata", "x", CLOSE - timedelta(hours=2), CLOSE - timedelta(hours=1))
    ports = _ports(news_items=[visible, late])
    report = run_once("EURUSD", CLOSE, ports, _cfg())
    assert len(ports.macro.calls) == 1 and report.features["macro"] == 2.0
    assert "dopo la chiusura" not in ports.macro.calls[0]["user"]


def test_llm_down_records_cycle_with_missing_features():
    down = FakeLlm([ConnectionError("ollama giù")] * 10)
    ports = _ports(tech=down)
    report = run_once("EURUSD", CLOSE, ports, _cfg())
    assert report.status == "done" and report.features["tecnico"] is None
    assert report.llm_invalid == ["tecnico"]
    assert ports.store.llm_calls[0][2].schema_valid is False  # il fallimento è in archivio


def test_market_error_records_cycle_error():
    ports = _ports(market=TableMarket(fail=True))
    report = run_once("EURUSD", CLOSE, ports, _cfg())
    assert report.status == "error" and "MT5" in report.error
    assert ports.store.finished[1]["status"] == "error"


def test_naive_candle_close_raises():
    with pytest.raises(ValueError):
        run_once("EURUSD", CLOSE.replace(tzinfo=None), _ports(), _cfg())
