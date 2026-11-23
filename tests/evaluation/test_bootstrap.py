"""P5.03: bootstrap appaiato che ricampiona giorni interi (preregistrazione §5) e sessioni di mercato."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from evaluation.bootstrap import B, SEED, cluster_ci, groups, session_of
from evaluation.metrics import brier

DAYS, PER_DAY = 60, 8


def _synthetic(mean=0.3, seed=1):
    rng = np.random.default_rng(seed)
    day_effect = np.repeat(rng.normal(0, 0.2, DAYS), PER_DAY)  # candidati dello stesso giorno correlati
    values = mean + day_effect + rng.normal(0, 0.5, DAYS * PER_DAY)
    return values, np.repeat(np.arange(DAYS), PER_DAY)


def test_defaults_are_the_preregistered_ones():
    assert (B, SEED) == (2000, 20261123)


def test_ci_contains_true_mean_synthetic():
    values, days = _synthetic()
    est, low, high = cluster_ci(lambda i: values[i].mean(), days)
    assert low < 0.3 < high and low < est < high


def test_cluster_ci_wider_than_naive_with_correlated_days():
    # ricampionare candidati come indipendenti darebbe un intervallo troppo stretto (il motivo della §5)
    values, days = _synthetic()
    _, low, high = cluster_ci(lambda i: values[i].mean(), days)
    _, nlow, nhigh = cluster_ci(lambda i: values[i].mean(), np.arange(len(values)))
    assert (high - low) > 1.3 * (nhigh - nlow)


def test_identical_variants_diff_ci_is_zero():
    values, days = _synthetic()
    y = (values > 0.3).astype(float)
    p = np.clip(values, 0.01, 0.99)
    assert cluster_ci(lambda i: brier(y[i], p[i]) - brier(y[i], p[i]), days) == (0.0, 0.0, 0.0)


def test_resamples_whole_days():
    _, days = _synthetic()
    _, low, high = cluster_ci(lambda i: float(len(i) % PER_DAY), days, n_boot=200)
    assert low == high == 0.0  # ogni campione è un'unione di giorni interi


def test_deterministic_with_seed():
    values, days = _synthetic()
    stat = lambda i: values[i].mean()  # noqa: E731
    assert cluster_ci(stat, days) == cluster_ci(stat, days)
    assert cluster_ci(stat, days, seed=1) != cluster_ci(stat, days)


def test_sessions_known_hours():
    d = datetime(2026, 3, 2, tzinfo=timezone.utc)
    assert [session_of(d.replace(hour=h)) for h in (22, 3, 7, 12, 13, 21)] == [
        "Asia", "Asia", "Londra", "Londra", "New York", "New York"]


def test_session_rejects_naive_datetime():
    with pytest.raises(ValueError):
        session_of(datetime(2026, 3, 2, 10))


@given(st.integers(0, 24 * 60 * 14 - 1))
def test_session_total_partition(minutes):
    t = datetime(2026, 3, 2, tzinfo=timezone.utc) + timedelta(minutes=minutes)
    assert session_of(t) in {"Asia", "Londra", "New York"}


def test_groups_partition_indices():
    g = groups(["EURUSD", "GBPUSD", "EURUSD"])
    assert {k: list(v) for k, v in g.items()} == {"EURUSD": [0, 2], "GBPUSD": [1]}
