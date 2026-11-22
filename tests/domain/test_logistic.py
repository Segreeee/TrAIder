"""P4.04: logistica L2 con offset logit(p0), walk-forward e regola di attivazione del modello."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.logistic import Row, brier_skill_score, choose_model, fit_offset_logistic, predict, walk_forward_fit

p0s = st.floats(min_value=0.05, max_value=0.95)
feat = st.floats(min_value=-3, max_value=3)
coef = st.floats(min_value=-2, max_value=2)


def _logit(p):
    return np.log(p / (1 - p))


@given(p0=p0s, x=st.lists(feat, min_size=2, max_size=2))
def test_beta_zero_gives_p0_exactly(p0, x):
    p = predict(np.array([x]), np.array([_logit(p0)]), np.zeros(2))
    assert p[0] == pytest.approx(p0, abs=1e-12)


@given(p0=p0s, x=st.lists(feat, min_size=2, max_size=2), b=st.lists(coef, min_size=2, max_size=2))
def test_p_in_open_interval(p0, x, b):
    p = predict(np.array([x]), np.array([_logit(p0)]), np.array(b))
    assert 0 < p[0] < 1


@given(p0=p0s, x=feat, dx=st.floats(min_value=0.01, max_value=3), b=st.floats(min_value=0.01, max_value=2))
def test_monotone_in_feature_with_positive_beta(p0, x, dx, b):
    off = np.array([_logit(p0)] * 2)
    p = predict(np.array([[x], [x + dx]]), off, np.array([b]))
    assert p[1] > p[0]


def test_synthetic_recovers_beta():
    rng = np.random.default_rng(11)
    n, true_beta = 5000, np.array([0.8, -0.5])
    X = rng.standard_normal((n, 2))
    offset = np.full(n, _logit(0.4))
    y = (rng.random(n) < predict(X, offset, true_beta)).astype(float)

    beta_hat = fit_offset_logistic(X, y, offset, l2=1.0)
    assert np.all(np.abs(beta_hat - true_beta) < 0.15)

    # calibrazione per decili: |media prevista − frequenza osservata| < 0.05 in ogni decile
    p_hat = predict(X, offset, beta_hat)
    for idx in np.array_split(np.argsort(p_hat), 10):
        assert abs(p_hat[idx].mean() - y[idx].mean()) < 0.05


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rows(n, rng, start):
    X = rng.standard_normal((n, 1))
    y = (rng.random(n) < predict(X, np.zeros(n), np.array([1.0]))).astype(float)
    return [Row(start + timedelta(hours=i), X[i], y[i], 0.0) for i in range(n)]


def test_walk_forward_ignores_future_rows():
    rng = np.random.default_rng(3)
    past = _rows(300, rng, T0)
    t = T0 + timedelta(hours=300)
    future = _rows(300, rng, t)  # dal cutoff t in poi: non si possono usare
    for r in future:
        r.x[:] = -r.x  # dati futuri con segno opposto: se trapelassero, il fit cambierebbe
    assert np.allclose(walk_forward_fit(past, t), walk_forward_fit(past + future, t))


def test_walk_forward_without_past_rows_returns_none():
    assert walk_forward_fit([], T0) is None


def test_brier_skill_score_known():
    y = np.array([1, 0, 1, 0])
    ref = np.full(4, 0.5)  # Brier di riferimento 0.25
    assert brier_skill_score(y, np.array([0.75, 0.25, 0.75, 0.25]), ref) == pytest.approx(0.75)
    assert brier_skill_score(y, ref, ref) == pytest.approx(0.0)


def test_choose_model_threshold_100():
    assert choose_model(n_resolved=99, bss=0.10) == "beta"
    assert choose_model(n_resolved=100, bss=0.10) == "logistica"


def test_choose_model_requires_positive_out_of_sample_skill():
    assert choose_model(n_resolved=5000, bss=0.0) == "beta"
    assert choose_model(n_resolved=5000, bss=-0.02) == "beta"
    assert choose_model(n_resolved=5000, bss=None) == "beta"


def test_bss_lower_bound_is_below_point_estimate_and_positive_for_real_skill():
    from domain.logistic import bss_lower_bound
    rng = np.random.default_rng(4)
    p_true = rng.uniform(0.2, 0.8, 2000)
    y = (rng.random(2000) < p_true).astype(float)
    ref = np.full(2000, 0.5)
    low = bss_lower_bound(y, p_true, ref)
    assert 0 < low < brier_skill_score(y, p_true, ref)
    assert bss_lower_bound(y, ref, ref) == pytest.approx(0.0)  # nessuna abilità: estremo inferiore 0
