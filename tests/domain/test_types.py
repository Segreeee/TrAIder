"""P3.06: tipi di dominio con geometria validata nel costruttore."""
from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.types import Candidate, Direction, HoldReason, levels_consistent

CLOSE = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)


def test_candidate_rejects_inverted_geometry():
    with pytest.raises(ValueError):
        Candidate("EURUSD", Direction.BUY, entry=1.10, sl=1.11, tp=1.09, candle_close_utc=CLOSE)


def test_candidate_rejects_naive_datetime():
    with pytest.raises(ValueError):
        Candidate("EURUSD", Direction.BUY, entry=1.10, sl=1.09, tp=1.12, candle_close_utc=datetime(2026, 11, 23))


def test_candidate_distances():
    c = Candidate("EURUSD", Direction.SELL, entry=1.1000, sl=1.1010, tp=1.0985, candle_close_utc=CLOSE)
    assert c.d_sl == pytest.approx(0.0010)
    assert c.d_tp == pytest.approx(0.0015)


def test_hold_reason_values_closed_set():
    assert {r.name for r in HoldReason} == {
        "NO_CANDIDATE", "GATE_EV", "SAME_SYMBOL", "EXPOSURE", "MAX_POSITIONS",
        "DAILY_LOSS", "LOT_BELOW_MIN", "LLM_INVALID",
    }


@given(
    direction=st.sampled_from(list(Direction)),
    entry=st.floats(min_value=0.5, max_value=200),
    d_sl=st.floats(min_value=1e-4, max_value=5),
    d_tp=st.floats(min_value=1e-4, max_value=5),
)
def test_valid_candidate_has_positive_distances(direction, entry, d_sl, d_tp):
    sign = 1 if direction is Direction.BUY else -1
    c = Candidate("EURUSD", direction, entry=entry, sl=entry - sign * d_sl, tp=entry + sign * d_tp,
                  candle_close_utc=CLOSE)
    assert c.d_sl > 0 and c.d_tp > 0


def test_candidate_rejects_stop_or_target_below_a_tenth_of_pip():
    # review di fine Fase 3 (R10): uno stop arrotondato a 0 pip faceva dividere per zero in decide e in p0
    with pytest.raises(ValueError, match="0.1 pip"):
        Candidate("EURUSD", Direction.BUY, entry=1.10000, sl=1.099999, tp=1.10010, candle_close_utc=CLOSE)
    with pytest.raises(ValueError, match="0.1 pip"):
        Candidate("EURUSD", Direction.SELL, entry=1.10000, sl=1.10010, tp=1.099999, candle_close_utc=CLOSE)
