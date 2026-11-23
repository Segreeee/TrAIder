"""P3.08: costi in pip, distanze arrotondate (T-009), R lordo/netto, simulatore di esito."""
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.costs import cost_pips, distance_pips
from domain.outcome import first_hit, realized_result, simulate_outcome


# --- costi ------------------------------------------------------------------ #
def test_cost_pips_known_case():
    # spread 12 punti a 5 cifre = 1.2 pip; commissione 7 EUR/lotto a/r con pip a 10 EUR = 0.7 pip; slippage 0.2
    c = cost_pips(spread_points=12, point=0.00001, pip_size=0.0001,
                  commission_eur_per_lot=7.0, pip_value_eur_per_lot=10.0, slippage_pips=0.2)
    assert c == pytest.approx(2.1)


def test_cost_pips_jpy_pair():
    # USDJPY a 3 cifre: spread 15 punti = 1.5 pip
    assert cost_pips(15, 0.001, 0.01, 0.0, 6.06, 0.0) == pytest.approx(1.5)


@given(spread=st.integers(min_value=0, max_value=200), comm=st.floats(min_value=0, max_value=20),
       slip=st.floats(min_value=0, max_value=5))
def test_cost_never_below_spread(spread, comm, slip):
    assert cost_pips(spread, 0.00001, 0.0001, comm, 9.0, slip) >= spread * 0.1 - 1e-9


def test_distance_pips_rounds_float_noise():
    # T-009: 1.1030 - 1.1000 in virgola mobile non dà esattamente 30 pip
    assert distance_pips(1.1000, 1.1030, 0.0001) == 30.0
    assert distance_pips(1.1000, 1.0980, 0.0001) == 20.0
    assert distance_pips(1.1000, 1.1030, 0.0001) / distance_pips(1.1000, 1.0980, 0.0001) >= 1.5


# --- R lordo/netto (stesse asserzioni dei CostsTest legacy) -------------------- #
def test_costs_reduce_r_multiple():
    res = realized_result("BUY", 1.1000, 1.1020, 1.0990, pip_size=0.0001, cost_pips=1.0)
    assert res["r_multiple_gross"] == pytest.approx(2.0)
    assert res["r_multiple"] == pytest.approx(1.9)
    assert res["pips"] == pytest.approx(19.0)


def test_costs_make_losses_bigger():
    res = realized_result("SELL", 1.1000, 1.1010, 1.1010, pip_size=0.0001, cost_pips=1.0)
    assert res["r_multiple"] == pytest.approx(-1.1)


@given(d_sl=st.integers(min_value=5, max_value=100), d_tp=st.integers(min_value=5, max_value=200),
       cost=st.floats(min_value=0, max_value=5), action=st.sampled_from(["BUY", "SELL"]))
def test_tp_outcome_r_gross_and_net(d_sl, d_tp, cost, action):
    sign = 1 if action == "BUY" else -1
    entry, pip = 1.2000, 0.0001
    res = realized_result(action, entry, entry + sign * d_tp * pip, entry - sign * d_sl * pip, pip, cost)
    assert res["r_multiple_gross"] == pytest.approx(d_tp / d_sl, abs=1e-3)
    assert res["r_multiple"] == pytest.approx(res["r_multiple_gross"] - cost / d_sl, abs=2e-3)


# --- simulatore di esito ----------------------------------------------------- #
def _bars(rows):
    return pd.DataFrame(rows, columns=["high", "low", "close"])


def test_sl_wins_when_ambiguous():
    assert simulate_outcome("BUY", tp=1.1020, sl=1.0990, future_df=_bars([(1.1030, 1.0980, 1.1000)])) == ("SL", 1.0990)


def test_tp_hit_first():
    bars = _bars([(1.1010, 1.0995, 1.1005), (1.1025, 1.1000, 1.1020)])
    assert simulate_outcome("BUY", 1.1020, 1.0990, bars) == ("TP", 1.1020)


def test_timeout_uses_last_close():
    bars = _bars([(1.1010, 1.0995, 1.1005), (1.1012, 1.0998, 1.1008)])
    assert simulate_outcome("SELL", 1.0950, 1.1050, bars) == ("TIMEOUT", 1.1008)


def test_timeout_without_bars():
    assert simulate_outcome("BUY", 1.1020, 1.0990, _bars([])) == ("TIMEOUT", None)


# --- T-010: le uscite dei SELL avvengono all'ask (bid + spread) -------------- #


def _one_bar(high, low):
    return pd.DataFrame({"high": [high], "low": [low], "close": [(high + low) / 2]})


def test_sell_tp_needs_the_ask_to_reach_it():
    # bid tocca il TP (1.0970) ma l'ask resta 0.8 pip sopra: per un SELL non è un'uscita
    assert first_hit("SELL", tp=1.0970, sl=1.1020, future_df=_one_bar(1.0990, 1.0970), spread=0.00008) is None


def test_sell_sl_hit_by_the_ask():
    # il bid si ferma 0.5 pip sotto lo SL, l'ask lo supera: per un SELL è stop
    assert first_hit("SELL", tp=1.0970, sl=1.1020, future_df=_one_bar(1.10195, 1.0990), spread=0.00008)[0] == "SL"


def test_buy_exits_ignore_spread():
    bar = _one_bar(1.1030, 1.0990)
    assert first_hit("BUY", 1.1030, 1.0980, bar, spread=0.00008) == first_hit("BUY", 1.1030, 1.0980, bar)
