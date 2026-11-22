"""P4.01: probabilità di base e payoff in R. Formule della Fase 4 (vedi domain/probability.py)."""
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from domain.probability import Payoff, ev, p0, payoff

# --- casi noti --------------------------------------------------------------- #


def test_p0_known():
    assert p0(d_sl=10, d_tp=15) == pytest.approx(0.4)


def test_p_star_known():
    assert payoff(d_sl=10, d_tp=15, cost=1).p_star == pytest.approx(11 / 25)


def test_ev_known():
    pay = payoff(d_sl=10, d_tp=15, cost=1)
    assert pay.win == pytest.approx(1.4) and pay.loss == pytest.approx(1.1)
    assert ev(p0(10, 15), pay) == pytest.approx(-0.1)


@pytest.mark.parametrize("d_sl, d_tp, cost", [(0, 10, 0), (10, 0, 0), (10, 15, -1), (10, 15, 15)])
def test_invalid_geometry_raises(d_sl, d_tp, cost):
    with pytest.raises(ValueError):
        payoff(d_sl, d_tp, cost)


# --- proprietà --------------------------------------------------------------- #
dist = st.floats(min_value=1, max_value=500)
costs = st.floats(min_value=0, max_value=20)
prob = st.floats(min_value=0, max_value=1)


@given(d_sl=dist, d_tp=dist, cost=costs)
def test_ev_at_p0_equals_minus_c_over_dsl(d_sl, d_tp, cost):
    assume(cost < d_tp)
    assert ev(p0(d_sl, d_tp), payoff(d_sl, d_tp, cost)) == pytest.approx(-cost / d_sl, abs=1e-9)


@given(d_sl=dist, d_tp=dist, extra=st.floats(min_value=0.1, max_value=100))
def test_p0_decreases_when_dtp_increases(d_sl, d_tp, extra):
    assert p0(d_sl, d_tp + extra) < p0(d_sl, d_tp)


@given(d_sl=dist, d_tp=dist, cost=costs)
def test_ev_zero_at_p_star(d_sl, d_tp, cost):
    assume(cost < d_tp)
    pay = payoff(d_sl, d_tp, cost)
    assert ev(pay.p_star, pay) == pytest.approx(0.0, abs=1e-9)


@given(d_sl=dist, d_tp=dist, cost=costs, a=prob, b=prob)
def test_ev_increasing_in_p(d_sl, d_tp, cost, a, b):
    # b − a ≥ 1e-6: con differenze subnormali (1e-308) le due EV coincidono in virgola mobile
    assume(cost < d_tp and b - a >= 1e-6)
    pay = payoff(d_sl, d_tp, cost)
    assert ev(a, pay) < ev(b, pay)


def test_payoff_is_frozen():
    pay = payoff(10, 15, 1)
    assert isinstance(pay, Payoff)
    with pytest.raises(AttributeError):
        pay.win = 2.0
