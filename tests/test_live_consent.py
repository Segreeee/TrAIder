"""P3.02 (T-006): un ordine reale richiede DUE consensi espliciti, dry_run=False e allow_live_trading=True.

Un solo flag non deve mai bastare per arrivare a order_send.
"""
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

import core.executor as ex

# BUY all'ask 1.10010: TP +10 pip, SL -6 pip -> R:R 1.67 (ben sopra 1.5, niente bordi in virgola mobile),
# quindi l'unico ostacolo all'invio è il consenso.
VALID_BUY = {
    "action": "BUY", "confidence_percentage": 60, "lot_size": 0.1,
    "take_profit_price": 1.10110, "stop_loss_price": 1.09950, "reasoning": "x",
}


class FakeMt5:
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, TRADE_ACTION_DEAL = 0, 1, 1
    ORDER_TIME_GTC, ORDER_FILLING_IOC, TRADE_RETCODE_DONE = 0, 1, 10009

    def __init__(self):
        self.sent = []

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=1.10010, bid=1.10000)

    def order_send(self, request):
        self.sent.append(request)
        return SimpleNamespace(retcode=10009, _asdict=lambda: {})


@pytest.fixture
def fake_mt5(monkeypatch):
    fake = FakeMt5()
    monkeypatch.setattr(ex, "mt5", fake)
    return fake


def _execute(dry_run, allow_live, fake):
    ex.OrderExecutor(dry_run=dry_run, allow_live_trading=allow_live).execute("EURUSD", dict(VALID_BUY))
    return fake.sent


def test_dry_run_false_alone_sends_no_order(fake_mt5):
    assert _execute(False, False, fake_mt5) == []


def test_allow_live_alone_sends_no_order(fake_mt5):
    assert _execute(True, True, fake_mt5) == []


def test_both_consents_reach_order_send(fake_mt5):
    assert len(_execute(False, True, fake_mt5)) == 1


def test_allow_live_defaults_to_false(fake_mt5):
    ex.OrderExecutor(dry_run=False).execute("EURUSD", dict(VALID_BUY))
    assert fake_mt5.sent == []


@given(dry_run=st.booleans(), allow_live=st.booleans())
def test_order_send_called_iff_double_consent(dry_run, allow_live):
    fake = FakeMt5()
    original = ex.mt5
    ex.mt5 = fake
    try:
        _execute(dry_run, allow_live, fake)
    finally:
        ex.mt5 = original
    assert (len(fake.sent) == 1) == ((not dry_run) and allow_live)


def test_settings_allow_live_trading_defaults_false():
    # Sostituito da test_defaults_are_safe quando la configurazione passa a pydantic-settings (P3.21).
    from config.settings import Settings
    assert Settings().allow_live_trading is False
