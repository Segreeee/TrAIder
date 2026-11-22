"""P4.01–P4.03: probabilità di base, payoff, posteriore Beta, Kelly e gate.
Formule della Fase 4 (vedi domain/probability.py)."""
import numpy as np
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from domain.probability import Payoff, beta_posterior, ev, ev5, p0, payoff

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


# --- P4.02: Beta con κ, p5, EV_5 -------------------------------------------- #

def test_no_data_mean_is_p0():
    assert beta_posterior(0.4, kappa=20, wins=0, losses=0).mean == pytest.approx(0.4)


@given(p=st.floats(min_value=0.05, max_value=0.95), w=st.integers(0, 500), l=st.integers(0, 500))
def test_p5_le_mean(p, w, l):
    post = beta_posterior(p, 20, w, l)
    assert post.quantile(0.05) <= post.mean


def test_more_data_narrows_interval():
    few = beta_posterior(0.4, 20, 4, 6)
    many = beta_posterior(0.4, 20, 400, 600)
    assert many.quantile(0.95) - many.quantile(0.05) < few.quantile(0.95) - few.quantile(0.05)


def test_synthetic_recovers_known_p():
    outcomes = np.random.default_rng(7).random(3000) < 0.45
    wins = int(outcomes.sum())
    post = beta_posterior(0.4, 20, wins, len(outcomes) - wins)
    assert abs(post.mean - 0.45) < 0.02


@given(p=st.floats(min_value=0.05, max_value=0.95), w=st.integers(0, 500), l=st.integers(0, 500),
       d_sl=dist, d_tp=dist, cost=costs)
def test_ev5_le_ev_mean(p, w, l, d_sl, d_tp, cost):
    assume(cost < d_tp)
    post, pay = beta_posterior(p, 20, w, l), payoff(d_sl, d_tp, cost)
    assert ev5(post, pay) <= ev(post.mean, pay) + 1e-12


@pytest.mark.parametrize("p, kappa, w, l", [(0.0, 20, 0, 0), (1.0, 20, 0, 0), (0.4, 0, 0, 0), (0.4, 20, -1, 0)])
def test_invalid_beta_inputs_raise(p, kappa, w, l):
    with pytest.raises(ValueError):
        beta_posterior(p, kappa, w, l)
