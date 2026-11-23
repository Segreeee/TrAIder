"""P3.22: indicatori e generatore di candidati baseline (senza LLM).
Direzione: chiusura vs EMA20 concorde con il trend H1 (chiusura vs EMA50). Ingresso al prezzo di
esecuzione atteso (ask = bid + spread per i BUY, bid per i SELL); SL = 1.0·ATR, TP = 1.5·ATR."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.candidates import generate
from app.features import add_indicators
from domain.probability import p0
from domain.types import Direction

START = datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)


def _bars(closes, freq_min, spread=8, start=START):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    return pd.DataFrame({
        "timestamp": pd.date_range(start, periods=len(closes), freq=f"{freq_min}min", tz="UTC"),
        "open": opens, "high": np.maximum(opens, closes) + 0.0003, "low": np.minimum(opens, closes) - 0.0003,
        "close": closes, "volume": 100, "spread": spread,
    })


def _trend(n, step, start=1.10):
    return start + step * np.arange(n) + 0.0002 * np.sin(np.arange(n))


M15_UP = _bars(_trend(200, 0.0001), 15)
H1_UP = _bars(_trend(120, 0.0004, start=1.09), 60, start=START - timedelta(hours=70))
H1_DOWN = _bars(_trend(120, -0.0004, start=1.12), 60, start=START - timedelta(hours=70))


def _close_of(bars):
    return bars["timestamp"].iloc[-1].to_pydatetime() + timedelta(minutes=15)


def test_known_bars_give_expected_candidate():
    cand, feats = generate("EURUSD", M15_UP, H1_UP, _close_of(M15_UP))
    ind = add_indicators(M15_UP).iloc[-1]
    entry = ind["close"] + 8 * 0.00001  # BUY all'ask: bid + 0.8 pip di spread
    assert cand.direction is Direction.BUY
    assert cand.entry == pytest.approx(entry)
    assert cand.sl == pytest.approx(entry - ind["atr"]) and cand.tp == pytest.approx(entry + 1.5 * ind["atr"])
    assert cand.candle_close_utc == _close_of(M15_UP)
    assert p0(cand.d_sl, cand.d_tp) == pytest.approx(0.4)
    assert set(feats) == {"momentum", "rsi_dev", "macd_hist_atr"} and feats["momentum"] > 0


def test_sell_entry_is_bid():
    m15_down = _bars(_trend(200, -0.0001, start=1.12), 15)
    cand, _ = generate("EURUSD", m15_down, H1_DOWN, _close_of(m15_down))
    assert cand.direction is Direction.SELL
    assert cand.entry == pytest.approx(m15_down["close"].iloc[-1])


def test_no_candidate_when_trend_disagrees():
    assert generate("EURUSD", M15_UP, H1_DOWN, _close_of(M15_UP)) is None


def test_no_candidate_when_atr_nan():
    short = M15_UP.tail(10).reset_index(drop=True)
    assert generate("EURUSD", short, H1_UP, _close_of(short)) is None


def test_jpy_spread_uses_jpy_point():
    m15 = _bars(_trend(200, 0.01, start=150.0), 15)
    h1 = _bars(_trend(120, 0.04, start=149.0), 60, start=START - timedelta(hours=70))
    cand, _ = generate("USDJPY", m15, h1, _close_of(m15))
    assert cand.entry == pytest.approx(m15["close"].iloc[-1] + 8 * 0.001)


def test_no_lookahead():
    # stesse barre fino alla chiusura, più barre future in coda: il candidato non cambia
    close = _close_of(M15_UP.head(150))
    future_m15 = pd.concat([M15_UP.head(150), _bars(_trend(50, -0.002, 1.2), 15, start=close)], ignore_index=True)
    future_h1 = pd.concat([H1_UP, _bars(_trend(30, -0.01, 1.3), 60, start=close)], ignore_index=True)
    assert generate("EURUSD", future_m15, future_h1, close) == generate("EURUSD", M15_UP.head(150), H1_UP, close)


@settings(max_examples=40)
@given(seed=st.integers(0, 10_000), drift=st.floats(-0.0002, 0.0002))
def test_generated_geometry_valid(seed, drift):
    rng = np.random.default_rng(seed)
    m15 = _bars(1.10 + np.cumsum(rng.normal(drift, 0.0005, 200)), 15)
    h1 = _bars(1.10 + np.cumsum(rng.normal(drift * 4, 0.001, 120)), 60, start=START - timedelta(hours=70))
    out = generate("EURUSD", m15, h1, _close_of(m15))
    if out is not None:
        cand, _ = out
        assert cand.d_tp / cand.d_sl == pytest.approx(1.5)
        assert all(-3 <= v <= 3 for v in out[1].values())


def test_stop_below_a_tenth_of_pip_gives_no_candidate():
    # R10: volatilità quasi nulla -> nessun candidato, non un ciclo in errore
    assert generate("EURUSD", M15_UP, H1_UP, _close_of(M15_UP), sl_atr=1e-6) is None
