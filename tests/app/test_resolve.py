"""P3.27: risoluzione virtuale di tutti i candidati (Q-004), eseguiti o no.
Solo barre aperte dalla chiusura in poi; TP/SL primo toccato (SL se ambigui); TIMEOUT a 96 barre;
R netto con il costo registrato nel candidato."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.resolve import resolve_pending
from domain.types import Candidate, Direction
from ports import CandidateRecord
from tests.fakes import FakeStore

CLOSE = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
M15 = timedelta(minutes=15)


class PathMarket:
    """Barre M15 con chiusure date: le barre `before` finiscono alla chiusura, `after` partono da lì."""

    def __init__(self, before, after, high_low=0.0002):
        closes = np.r_[before, after].astype(float)
        start = CLOSE - M15 * len(before)
        self.df = pd.DataFrame({
            "timestamp": pd.date_range(start, periods=len(closes), freq="15min", tz="UTC"),
            "open": closes, "high": closes + high_low, "low": closes - high_low, "close": closes,
            "volume": 100, "spread": 8,
        })
        self.requests = []

    def closed_bars(self, symbol, timeframe, count):
        self.requests.append(count)
        return self.df.tail(count).reset_index(drop=True)

    def eur_quote_rate(self, symbol):
        return 1.10


def _store_with(direction=Direction.BUY, entry=1.1000, sl=1.0980, tp=1.1030, cost=1.0, variant="v2-tecnica"):
    store = FakeStore()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    cand = Candidate("EURUSD", direction, entry, sl, tp, CLOSE)
    cid = store.record_candidate(cycle, CandidateRecord(variant, cand, cost, 0.4, 0.42, -0.05, -0.2, "HOLD", "GATE_EV"))
    return store, cid


def _now(market):
    return market.df["timestamp"].iloc[-1].to_pydatetime() + M15


def test_resolves_non_executed_candidates():
    store, cid = _store_with()
    market = PathMarket(before=[1.1000] * 5, after=[1.1010, 1.1020, 1.1035])  # sale fino al TP
    assert resolve_pending(store, market, _now(market)) == 1
    out = store.outcomes[cid]
    assert (out.result, out.exit_price, out.resolved_by) == ("TP", 1.1030, "virtuale")
    assert out.resolved_at == CLOSE + 3 * M15  # chiusura della barra che tocca il TP


def test_never_uses_bars_up_to_close():
    # la barra che chiude ALLA chiusura del candidato tocca lo SL: non conta, è il passato
    store, cid = _store_with()
    market = PathMarket(before=[1.1000] * 4 + [1.0970], after=[1.1010, 1.1035])
    resolve_pending(store, market, _now(market))
    assert store.outcomes[cid].result == "TP"


def test_sl_wins_when_both_in_same_bar():
    store, cid = _store_with()
    market = PathMarket(before=[1.1000] * 5, after=[1.1005], high_low=0.0030)  # tocca entrambi
    resolve_pending(store, market, _now(market))
    assert store.outcomes[cid].result == "SL"


def test_waits_when_not_enough_bars():
    store, cid = _store_with()
    market = PathMarket(before=[1.1000] * 5, after=[1.1001] * 10)  # niente TP/SL e meno di 96 barre
    assert resolve_pending(store, market, _now(market)) == 0
    assert cid not in store.outcomes


def test_timeout_after_horizon():
    store, cid = _store_with()
    market = PathMarket(before=[1.1000] * 5, after=[1.1001] * 100)
    resolve_pending(store, market, _now(market))
    out = store.outcomes[cid]
    assert out.result == "TIMEOUT" and out.resolved_at == CLOSE + 96 * M15


def test_r_net_uses_recorded_cost():
    store, cid = _store_with(cost=2.0)  # BUY 1.1000, SL 20 pip, TP 30 pip
    market = PathMarket(before=[1.1000] * 5, after=[1.1035])
    resolve_pending(store, market, _now(market))
    out = store.outcomes[cid]
    assert out.r_gross == pytest.approx(1.5) and out.r_net == pytest.approx(1.4)  # (30 − 2) / 20


def test_sell_candidate():
    store, cid = _store_with(direction=Direction.SELL, entry=1.1000, sl=1.1020, tp=1.0970)
    market = PathMarket(before=[1.1000] * 5, after=[1.0990, 1.0965])
    resolve_pending(store, market, _now(market))
    assert store.outcomes[cid].result == "TP" and store.outcomes[cid].r_net == pytest.approx(1.45)


def test_idempotent():
    store, cid = _store_with()
    market = PathMarket(before=[1.1000] * 5, after=[1.1035])
    assert resolve_pending(store, market, _now(market)) == 1
    assert resolve_pending(store, market, _now(market)) == 0
    assert len(store.outcomes) == 1


def test_asks_enough_bars_to_cover_the_candidate():
    store, _ = _store_with()
    market = PathMarket(before=[1.1000] * 5, after=[1.1001] * 40)
    resolve_pending(store, market, _now(market))
    assert market.requests and market.requests[0] >= 41  # tutte le barre dalla chiusura a ora
