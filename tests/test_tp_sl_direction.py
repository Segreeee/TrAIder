"""P3.03 (T-004): il gate R:R non deve accettare livelli invertiti.

Prima il rapporto era calcolato con abs(): un BUY con TP sotto l'ingresso e SL sopra
superava il controllo e poteva arrivare al broker.
"""
from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

import core.executor as ex
from core.risk_manager import levels_consistent, meets_min_risk_reward


def test_buy_with_tp_below_entry_rejected():
    assert not meets_min_risk_reward(1.1000, 1.0970, 1.1020, action="BUY")


def test_sell_with_tp_above_entry_rejected():
    assert not meets_min_risk_reward(1.1000, 1.1030, 1.0980, action="SELL")


def test_valid_buy_and_sell_still_pass():
    assert meets_min_risk_reward(1.1000, 1.1030, 1.0980, action="BUY")
    assert meets_min_risk_reward(1.1000, 1.0970, 1.1020, action="SELL")


def test_levels_consistent_known_cases():
    assert levels_consistent("BUY", 1.10, 1.11, 1.09)
    assert levels_consistent("SELL", 1.10, 1.09, 1.11)
    assert not levels_consistent("BUY", 1.10, 1.09, 1.11)
    assert not levels_consistent("SELL", 1.10, 1.11, 1.09)
    assert not levels_consistent("BUY", 1.10, 1.10, 1.09)  # TP all'ingresso
    assert not levels_consistent("HOLD", 1.10, 1.11, 1.09)


prices = st.floats(min_value=0.5, max_value=200.0, allow_nan=False, allow_infinity=False)


@given(action=st.sampled_from(["BUY", "SELL"]), entry=prices, tp=prices, sl=prices)
def test_rr_gate_never_accepts_inverted_levels(action, entry, tp, sl):
    inverted = (tp <= entry or sl >= entry) if action == "BUY" else (tp >= entry or sl <= entry)
    if inverted:
        assert not meets_min_risk_reward(entry, tp, sl, action=action)


def test_executor_never_sends_inverted_buy(monkeypatch):
    sent = []

    class FakeMt5:
        ORDER_TYPE_BUY, ORDER_TYPE_SELL, TRADE_ACTION_DEAL = 0, 1, 1
        ORDER_TIME_GTC, ORDER_FILLING_IOC, TRADE_RETCODE_DONE = 0, 1, 10009

        def symbol_info_tick(self, symbol):
            return SimpleNamespace(ask=1.10010, bid=1.10000)

        def order_send(self, request):
            sent.append(request)
            return SimpleNamespace(retcode=10009, _asdict=lambda: {})

    monkeypatch.setattr(ex, "mt5", FakeMt5())
    # BUY con TP 30 pip SOTTO l'ask e SL 10 pip SOPRA: con abs() il rapporto valeva 3.0.
    inverted_buy = {"action": "BUY", "confidence_percentage": 60, "lot_size": 0.1,
                    "take_profit_price": 1.09710, "stop_loss_price": 1.10110, "reasoning": "x"}
    ex.OrderExecutor(dry_run=False, allow_live_trading=True).execute("EURUSD", inverted_buy)
    assert sent == []
