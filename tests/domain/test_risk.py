"""P3.09: dimensione del lotto. Invarianti: lotto = 0 oppure >= minimo; rischio (costo incluso) <= limite."""
import math

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from domain.risk import lot_size

MIN_LOT, STEP, MAX_LOT = 0.01, 0.01, 5.0


def _lot(equity, risk_pct, d_sl, cost, pip_value):
    return lot_size(equity, risk_pct, d_sl, cost, pip_value, MIN_LOT, STEP, MAX_LOT)


def test_eurusd_normal_case():
    # 10 000 EUR all'1% = 100 EUR; 20 pip a 9.0909 EUR/pip/lotto -> 0.55 lotti
    assert _lot(10_000, 1.0, 20, 0.0, 9.0909) == pytest.approx(0.55)


def test_cost_counts_as_risk():
    # stesso caso con 2 pip di costo: 100 / (22 * 9.0909) = 0.5000005 -> 0.50 (senza costo 0.55)
    assert _lot(10_000, 1.0, 20, 2.0, 9.0909) == pytest.approx(0.50)


def test_lot_below_minimum_means_no_trade():
    # 20 EUR all'1% = 0.20 EUR; 10 pip a 9.09 -> 0.0022 lotti, sotto il minimo
    assert _lot(20, 1.0, 10, 0.0, 9.09) == 0.0


def test_zero_stop_means_no_trade():
    assert _lot(10_000, 1.0, 0.0, 0.0, 9.09) == 0.0


def test_capped_at_max_lot():
    assert _lot(10_000_000, 2.0, 5, 0.0, 9.09) == MAX_LOT


@pytest.mark.parametrize("equity, risk_pct", [(0, 1.0), (-5, 1.0), (1000, 0.0), (1000, 101.0)])
def test_invalid_inputs_raise(equity, risk_pct):
    with pytest.raises(ValueError):
        _lot(equity, risk_pct, 10, 0.0, 9.09)


inputs = dict(
    equity=st.floats(min_value=10, max_value=1e7),
    risk_pct=st.floats(min_value=0.01, max_value=5.0),
    d_sl=st.floats(min_value=0.5, max_value=500),
    cost=st.floats(min_value=0.0, max_value=10),
    pip_value=st.floats(min_value=0.5, max_value=20),
)


@given(**inputs)
def test_lot_zero_or_at_least_min(equity, risk_pct, d_sl, cost, pip_value):
    lot = _lot(equity, risk_pct, d_sl, cost, pip_value)
    assert lot == 0.0 or lot >= MIN_LOT


@given(**inputs)
def test_risk_never_exceeds_limit(equity, risk_pct, d_sl, cost, pip_value):
    lot = _lot(equity, risk_pct, d_sl, cost, pip_value)
    assert lot * (d_sl + cost) * pip_value <= equity * risk_pct / 100 * (1 + 1e-9)


@given(**inputs)
def test_lot_is_multiple_of_step_and_le_max(equity, risk_pct, d_sl, cost, pip_value):
    lot = _lot(equity, risk_pct, d_sl, cost, pip_value)
    assume(lot > 0)
    assert lot <= MAX_LOT
    assert math.isclose(round(lot / STEP) * STEP, lot, abs_tol=1e-9)
