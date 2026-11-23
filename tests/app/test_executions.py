"""P3.34: costi reali di esecuzione (spread, slippage, commissione, swap) e riconciliazione
tra esito virtuale ed esito del broker, con lo scarto in R (soglia D-008: 0.1 R).
Segni come in MT5: commissione e swap negativi = pagati."""
from types import SimpleNamespace

import pytest

from adapters.mt5_broker import Mt5Broker
from adapters.sim_broker import SimBroker
from adapters.sqlite_store import SqliteStore
from app.config import Settings
from app.resolve import reconcile_broker
from app.run_once import run_once
from domain.outcome import reconciliation_gap
from domain.types import Candidate, Direction
from ports import CandidateRecord, ClosedTrade, Fill, OrderRequest, Outcome
from tests.app.test_archive_completeness import _with_history
from tests.app.test_run_once import CLOSE, _ports, _quote
from tests.fakes import FakeMt5

NOW = CLOSE


def test_sim_execution_records_spread():
    store = _with_history(SqliteStore(":memory:"))
    ports = _ports(store=store, broker=SimBroker(quote=_quote, commission_eur_per_lot=7.0))
    report = run_once("EURUSD", CLOSE, ports, Settings(_env_file=None, commission_eur_per_lot=7.0))
    assert report.decision == "TRADE"
    cur = store.conn.execute("SELECT * FROM executions")
    (ex,) = [dict(zip([d[0] for d in cur.description], r, strict=True)) for r in cur.fetchall()]
    assert ex["mode"] == "sim" and ex["accepted"] == 1
    assert ex["spread"] == pytest.approx(0.00008)
    assert ex["commission"] == pytest.approx(-3.5 * ex["lots"])  # metà del giro, pagata all'ingresso
    sign = 1 if report.candidate.direction is Direction.BUY else -1
    assert ex["slippage"] == pytest.approx(sign * (ex["fill_price"] - report.candidate.entry) / 0.0001)


def test_mt5_deal_costs_recorded():
    mt5 = FakeMt5(NOW)
    mt5.commission_per_lot_side = -3.5
    broker = Mt5Broker(mt5, magic=990011, live_allowed=True, clock=lambda: NOW)
    bid, ask = mt5.ticks["EURUSD"]
    fill = broker.submit(OrderRequest("EURUSD", Direction.BUY, 0.10, sl=ask - 0.0020, tp=ask + 0.0030))
    assert fill.accepted and fill.commission == pytest.approx(-0.35)
    assert broker.closed_trade(fill.ticket) is None  # ancora aperta

    mt5.close_position(fill.ticket, price=ask + 0.0030, profit=27.27, swap=-0.20)
    closed = broker.closed_trade(fill.ticket)
    assert closed == ClosedTrade(exit_price=pytest.approx(ask + 0.0030), profit_eur=27.27,
                                 commission_eur=pytest.approx(-0.70), swap_eur=-0.20)


class _ClosedBroker:
    def __init__(self, trades):
        self.trades = trades

    def closed_trade(self, ticket):
        return self.trades.get(ticket)


def test_reconciliation_gap_in_r():
    store = SqliteStore(":memory:")
    cand = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, CLOSE)
    cid = store.record_candidate(store.begin_cycle("EURUSD", CLOSE), CandidateRecord(
        "v7-completo", cand, 0.2, 0.45, 0.42, 0.1, 0.05, "TRADE", None, p0=0.4, p5=0.41, lot=0.1, features={}))
    store.record_execution(cid, Fill("mt5", True, 1.1001, 0.00008, 7, commission=-0.35), lots=0.1, slippage_pips=1.0)
    store.record_outcome(cid, Outcome("TP", 1.1030, r_net=1.45, r_gross=1.5, resolved_by="virtuale", resolved_at=CLOSE))
    broker = _ClosedBroker({7: ClosedTrade(exit_price=1.1030, profit_eur=26.36, commission_eur=-0.70, swap_eur=-0.20)})
    market = SimpleNamespace(eur_quote_rate=lambda s: 1.10)

    assert reconcile_broker(store, broker, market) == 1
    assert reconcile_broker(store, broker, market) == 0  # già riconciliato

    # lordo: (1.1030 − 1.1001) / (1.1001 − 1.0980) = 29/21 = 1.381 R
    # costi: −0.90 EUR su un rischio di 21 pip × 0.909 EUR/pip (0.1 lotti, EURUSD a 1.10) = 19.09 EUR → −0.047 R
    ((_, virtual, real),) = store.reconciliations()
    assert real == pytest.approx(1.334, abs=1e-3)
    gap, too_big = reconciliation_gap(virtual, real)
    assert gap == pytest.approx(-0.116, abs=1e-3) and too_big  # oltre 0.1 R: nuova ADR secondo D-008


def test_small_gap_is_within_threshold():
    assert reconciliation_gap(1.45, 1.40) == (pytest.approx(-0.05), False)


def test_one_bad_trade_does_not_block_reconciliation(caplog):
    # review di fine Fase 3 (R8): un trade con dati anomali bloccava la riconciliazione di tutti gli altri
    store = SqliteStore(":memory:")
    cycle = store.begin_cycle("EURUSD", CLOSE)
    cand = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, CLOSE)
    ids = []
    for variant, ticket, fill_price in (("v1-p0", 7, 1.0980), ("v7-completo", 8, 1.1001)):  # il primo: fill sullo stop
        cid = store.record_candidate(cycle, CandidateRecord(variant, cand, 0.2, 0.45, 0.42, 0.1, 0.05, "TRADE", None,
                                                            p0=0.4, p5=0.41, lot=0.1, features={}))
        store.record_execution(cid, Fill("mt5", True, fill_price, 0.00008, ticket), lots=0.1, slippage_pips=0.0)
        ids.append(cid)
    closed = ClosedTrade(exit_price=1.1030, profit_eur=26.36, commission_eur=-0.70, swap_eur=0.0)
    broker = _ClosedBroker({7: closed, 8: closed})
    assert reconcile_broker(store, broker, SimpleNamespace(eur_quote_rate=lambda s: 1.10)) == 1
    assert [cid for cid, *_ in store.open_broker_trades()] == [ids[0]]  # resta in attesa, non perso
    assert "riconciliazione" in caplog.text
