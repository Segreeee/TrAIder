"""P3.25–P3.26: run_once su porte finte. Dati → candidato → analisti LLM → varianti → decisione → archivio.
Idempotenza per candela, macro solo con notizie visibili, LLM giù = caratteristiche mancanti,
tutte le varianti sullo stesso candidato, solo la variante di produzione arriva al broker."""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from adapters.sim_broker import SimBroker
from app.config import Settings
from app.run_once import Ports, broker_from_settings, run_once
from domain.types import Candidate, Direction
from ports import CandidateRecord, NewsItem, Outcome
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

    def eur_quote_rate(self, symbol):
        return 1.10


CLOSE = START + timedelta(minutes=15 * 200)  # chiusura dell'ultima barra M15


def _quote(symbol):
    bid = float(TableMarket().m15["close"].iloc[-1])  # prezzo corrente = ultima chiusura, spread 0.8 pip
    return bid, bid + 0.00008


def _ports(market=None, news_items=(), tech=None, macro=None, store=None, broker=None):
    return Ports(market=market or TableMarket(), news=FakeNews(CLOSE, items=list(news_items)),
                 technical=tech or FakeLlm([VIEW_BUY] * 5), macro=macro or FakeLlm([VIEW_BUY] * 5),
                 store=store or FakeStore(), broker=broker or SimBroker(quote=_quote))


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


# --- P3.26: varianti e decisione ---------------------------------------------- #


def test_all_variants_share_same_candidate():
    ports = _ports(news_items=[NewsItem("BCE", "x", CLOSE - timedelta(hours=2), CLOSE - timedelta(hours=1))])
    run_once("EURUSD", CLOSE, ports, _cfg())
    recs = [r for _, r in ports.store.candidates.values()]
    assert {r.variant for r in recs} == {"v1-p0", "v2-tecnica", "v3-llm-tecnico", "v4-llm-macro", "v5-consenso",
                                         "v7-completo"}
    assert len({r.candidate for r in recs}) == 1


def test_macro_variants_not_recorded_without_news():
    ports = _ports()
    run_once("EURUSD", CLOSE, ports, _cfg())
    variants = {r.variant for _, r in ports.store.candidates.values()}
    assert "v4-llm-macro" not in variants and "v5-consenso" not in variants and "v7-completo" in variants


def test_gate_closed_submits_nothing():
    # Q-004: senza esiti risolti p = p0 e con costo > 0 il gate resta chiuso per tutte le varianti
    ports = _ports()
    run_once("EURUSD", CLOSE, ports, _cfg())
    recs = [r for _, r in ports.store.candidates.values()]
    assert all(r.decision == "HOLD" and r.hold_reason == "GATE_EV" for r in recs)
    assert ports.broker.positions() == [] and ports.store.executions == []


class LosingBroker(SimBroker):
    def account(self):
        acc = super().account()
        return acc.__class__(acc.equity - 400, acc.open_positions, -400.0)


def test_daily_loss_stops_before_llm():
    ports = _ports(broker=LosingBroker(quote=_quote))
    run_once("EURUSD", CLOSE, ports, _cfg())
    assert ports.technical.calls == [] and ports.macro.calls == []
    prod = [r for _, r in ports.store.candidates.values() if r.variant == "v7-completo"][0]
    assert prod.hold_reason == "DAILY_LOSS"


def test_edge_in_history_submits_production_only():
    # storico risolto con il 70% di TP (p* ≈ 0.42): con 300 esiti la Beta apre il gate
    store = FakeStore()
    for i in range(300):
        cycle = store.begin_cycle("EURUSD", START - timedelta(days=60) + timedelta(minutes=15 * i))
        cand = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, START - timedelta(days=60))
        for variant in ("v7-completo", "v2-tecnica"):
            cid = store.record_candidate(cycle, CandidateRecord(variant, cand, 1.0, 0.4, 0.42, 0.0, 0.0, "HOLD",
                                                                "GATE_EV", p0=0.4, features={}))
            store.record_outcome(cid, Outcome("TP" if i % 10 < 7 else "SL", None, None, None, "virtuale", START))
    ports = _ports(store=store)
    report = run_once("EURUSD", CLOSE, ports, _cfg())
    assert report.decision == "TRADE"
    held = ports.broker.positions()
    assert [(p.symbol, p.direction) for p in held] == [("EURUSD", Direction.BUY)]
    assert len(ports.store.executions) == 1  # la sola variante di produzione arriva al broker
    v2 = [r for cid, (_, r) in ports.store.candidates.items() if r.variant == "v2-tecnica" and cid > 600][0]
    assert v2.decision == "TRADE"  # decisione virtuale registrata, ma nessun ordine


def test_default_broker_is_sim():
    calls = []
    broker = broker_from_settings(_cfg(), make_live=lambda: calls.append(1),
                                  make_sim=lambda: SimBroker(quote=lambda s: (1.1, 1.1001)))
    assert isinstance(broker, SimBroker) and calls == []

def test_cost_excludes_spread():
    # T-010: le distanze partono già dal prezzo di esecuzione (ask per i BUY): il costo è
    # commissione + slippage, senza contare lo spread una seconda volta
    ports = _ports()
    run_once("EURUSD", CLOSE, ports, Settings(_env_file=None, commission_eur_per_lot=7.0, slippage_pips=0.2))
    rec = next(r for _, r in ports.store.candidates.values())
    assert rec.cost_pips == pytest.approx(7.0 / (0.0001 * 100_000 / 1.10) + 0.2)


# --- log per simbolo (dopo il primo avvio reale: cicli lunghi e salti silenziosi) --- #


def _messages(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "app.run_once"]


def test_logs_one_summary_line_per_symbol(caplog):
    caplog.set_level("INFO")
    run_once("EURUSD", CLOSE, _ports(), _cfg())
    summary = [m for m in _messages(caplog) if m.startswith("EURUSD")]
    assert len(summary) == 1
    assert "BUY" in summary[0] and "HOLD" in summary[0] and "GATE_EV" in summary[0]


def test_logs_no_candidate(caplog):
    caplog.set_level("INFO")
    run_once("EURUSD", CLOSE, _ports(market=TableMarket(h1_step=-0.0004)), _cfg())
    assert any(m.startswith("EURUSD") and "nessun candidato" in m for m in _messages(caplog))


def test_logs_already_processed_candle(caplog):
    caplog.set_level("INFO")
    ports = _ports()
    run_once("EURUSD", CLOSE, ports, _cfg())
    caplog.clear()
    run_once("EURUSD", CLOSE, ports, _cfg())
    assert any(m.startswith("EURUSD") and "già elaborata" in m for m in _messages(caplog))


def test_logs_llm_start_before_waiting(caplog):
    caplog.set_level("INFO")
    run_once("EURUSD", CLOSE, _ports(), _cfg())
    assert any("tecnico" in m and "fake-llm" in m for m in _messages(caplog))


def test_stale_bars_close_cycle_as_error_before_llm():
    # review di fine Fase 3 (R6): se MT5 non ha ancora la barra nuova, l'ultima barra chiusa è quella
    # precedente; il ciclo decideva su dati vecchi di una candela registrandoli come se fossero nuovi
    ports = _ports()
    report = run_once("EURUSD", CLOSE + timedelta(minutes=15), ports, _cfg())
    assert report.status == "error" and "non ancora disponibile" in report.error
    assert ports.technical.calls == [] and ports.store.candidates == {}
