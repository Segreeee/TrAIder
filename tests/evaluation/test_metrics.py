"""P5.02: metriche della preregistrazione (§4) su valori calcolati a mano, più proprietà (hypothesis)."""
from datetime import datetime, timezone

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from evaluation.metrics import (auc, brier, brier_skill, calibration_deciles, ev_predicted_vs_realized, log_loss,
                                max_drawdown, summarize_r)
from ports import Outcome

T = datetime(2026, 3, 2, tzinfo=timezone.utc)
Y = [1, 0, 1, 0]
P = [0.8, 0.3, 0.6, 0.1]


def test_brier_known_value():
    # ((0.2)² + (0.3)² + (0.4)² + (0.1)²) / 4 = (0.04 + 0.09 + 0.16 + 0.01) / 4 = 0.075
    assert brier(Y, P) == pytest.approx(0.075)


def test_bss_known_value():
    # riferimento costante 0.4: ((0.6)² + (0.4)² + (0.6)² + (0.4)²) / 4 = 0.26 → BSS = 1 − 0.075/0.26
    assert brier_skill(Y, P, [0.4] * 4) == pytest.approx(1 - 0.075 / 0.26)


def test_bss_of_reference_is_zero():
    ref = [0.4, 0.4, 0.35, 0.5]
    assert brier_skill(Y, ref, ref) == pytest.approx(0.0)


def test_log_loss_known_value():
    expected = -np.mean([np.log(0.8), np.log(0.7), np.log(0.6), np.log(0.9)])
    assert log_loss(Y, P) == pytest.approx(expected)


def test_log_loss_finite_at_extremes():
    assert np.isfinite(log_loss([1, 0], [0.0, 1.0]))  # probabilità clippate, mai infinito


def test_auc_known_value_and_single_class():
    assert auc(Y, P) == pytest.approx(1.0)  # ogni TP ha p più alta di ogni SL
    assert auc([1, 0, 1, 0], [0.2, 0.8, 0.6, 0.4]) == pytest.approx(0.25)
    assert auc([1, 1], [0.3, 0.6]) is None  # non definita con una sola classe


def test_calibration_deciles_counts_and_means():
    p = np.linspace(0.05, 0.95, 20)
    y = (np.arange(20) % 2).astype(int)
    bins = calibration_deciles(y, p)
    assert len(bins) == 10 and sum(b["n"] for b in bins) == 20
    assert bins[0]["p_mean"] == pytest.approx(np.mean(p[:2])) and bins[0]["y_rate"] == pytest.approx(0.5)
    assert all(a["p_mean"] <= b["p_mean"] for a, b in zip(bins, bins[1:], strict=False))


def test_drawdown_monotone_series_zero():
    assert max_drawdown([0.5, 1.0, 0.2, 1.4]) == 0.0
    assert max_drawdown([]) == 0.0


def test_drawdown_known_value():
    # cumulata 1, 2, 1, -0.5, 0.5: picco 2, minimo successivo −0.5 → 2.5 R
    assert max_drawdown([1, 1, -1, -1.5, 1]) == pytest.approx(2.5)


def test_summary_reports_gross_and_net():
    # porting di CostsTest.test_summary_reports_gross_and_net (legacy, rimandato qui da P3.29)
    out = [Outcome("TP", 1.102, r_net=1.9, r_gross=2.0, resolved_by="virtuale", resolved_at=T),
           Outcome("SL", 1.099, r_net=-1.1, r_gross=-1.0, resolved_by="virtuale", resolved_at=T)]
    s = summarize_r(out)
    assert s["total_r_net"] == pytest.approx(0.8) and s["total_r_gross"] == pytest.approx(1.0)
    assert (s["n"], s["tp"], s["sl"], s["timeout"]) == (2, 1, 1, 0) and s["mean_r_net"] == pytest.approx(0.4)


def test_ev_predicted_vs_realized():
    r = ev_predicted_vs_realized([0.1, -0.2, 0.4], [1.5, -1.0, 0.1])
    assert r["predicted"] == pytest.approx(0.1) and r["realized"] == pytest.approx(0.2)
    assert r["gap"] == pytest.approx(0.1)


def test_mismatched_lengths_rejected():
    with pytest.raises(ValueError):
        brier([1, 0], [0.5])


probs = st.lists(st.floats(0, 1), min_size=1, max_size=50)


@given(probs, st.data())
def test_brier_between_zero_and_one(p, data):
    y = data.draw(st.lists(st.integers(0, 1), min_size=len(p), max_size=len(p)))
    assert 0.0 <= brier(y, p) <= 1.0


@given(st.lists(st.floats(-5, 5), max_size=60))
def test_drawdown_is_never_negative(r):
    assert max_drawdown(r) >= 0.0
