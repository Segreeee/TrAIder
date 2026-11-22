"""P3.16: broker MT5. Solo FakeMt5 iniettato: nessun terminale, nessun ordine reale.
Difesa in profondità: il costruttore rifiuta di partire senza consenso esplicito, e submit
ricontrolla direzione e R:R al prezzo ask/bid prima di qualunque richiesta."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from adapters.mt5_broker import Mt5Broker
from domain.types import Direction
from ports import AccountState, Broker, OrderRequest
from tests.contracts.broker_contract import check_broker
from tests.fakes import FakeMt5

NOW = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)


def _broker(mt5, magic=7):
    return Mt5Broker(mt5, magic=magic, live_allowed=True, clock=lambda: NOW)


def test_mt5_broker_honours_contract():
    mt5 = FakeMt5(NOW)
    check_broker(_broker(mt5), "EURUSD", *mt5.ticks["EURUSD"])
    assert isinstance(_broker(FakeMt5(NOW)), Broker)


@pytest.mark.parametrize("flag", [False, None, "true", 1])
def test_constructor_refuses_without_live_allowed(flag):
    with pytest.raises(PermissionError):
        Mt5Broker(FakeMt5(NOW), magic=7, live_allowed=flag)


def test_order_not_sent_when_spread_breaks_risk_reward():
    # Porting di ExecutorRealPriceTest: sulla chiusura R:R 1.5, all'ask (spread 1 pip) 0.67.
    mt5 = FakeMt5(NOW, ticks={"EURUSD": (1.10000, 1.10010)})
    fill = _broker(mt5).submit(OrderRequest("EURUSD", Direction.BUY, 0.1, sl=1.09980, tp=1.10030))
    assert not fill.accepted and "R:R" in fill.reason
    assert mt5.sent == []


@given(direction=st.sampled_from([Direction.BUY, Direction.SELL]),
       sl_pips=st.integers(1, 100), tp_pips=st.integers(1, 100))
def test_inverted_levels_never_sent(direction, sl_pips, tp_pips):
    mt5 = FakeMt5(NOW)
    bid, ask = mt5.ticks["EURUSD"]
    price, sign = (ask, 1) if direction is Direction.BUY else (bid, -1)
    # livelli dal lato sbagliato: SL oltre il prezzo nella direzione del profitto, TP dall'altra parte
    order = OrderRequest("EURUSD", direction, 0.1, sl=price + sign * sl_pips * 1e-4, tp=price - sign * tp_pips * 1e-4)
    assert not _broker(mt5).submit(order).accepted
    assert mt5.sent == []


def test_rejected_by_terminal_is_reported_not_raised():
    mt5 = FakeMt5(NOW)
    mt5.retcode = 10019  # fondi insufficienti
    fill = _broker(mt5).submit(OrderRequest("EURUSD", Direction.BUY, 0.1, sl=1.0980, tp=1.1040))
    assert not fill.accepted and "10019" in fill.reason
    assert _broker(mt5).positions() == []


def test_request_carries_magic_and_execution_price():
    mt5 = FakeMt5(NOW)
    fill = _broker(mt5, magic=42).submit(OrderRequest("EURUSD", Direction.SELL, 0.2, sl=1.1030, tp=1.0960))
    req = mt5.sent[0]
    assert req["magic"] == 42 and req["price"] == 1.10000 and req["type"] == mt5.ORDER_TYPE_SELL
    assert fill.accepted and fill.mode == "mt5" and fill.fill_price == 1.10000


def test_positions_only_for_our_magic():
    mt5 = FakeMt5(NOW)
    mt5.open_positions.append(SimpleNamespace(symbol="GBPUSD", type=1, volume=1.0, price_open=1.3, sl=1.31,
                                              tp=1.28, magic=99, ticket=500, profit=50.0))
    _broker(mt5).submit(OrderRequest("EURUSD", Direction.BUY, 0.1, sl=1.0980, tp=1.1040))
    assert [p.symbol for p in _broker(mt5).positions()] == ["EURUSD"]


# --- porting di AccountStateTest ---------------------------------------------- #


def test_reads_equity_positions_and_today_pnl_for_our_magic_only():
    mt5 = FakeMt5(NOW)
    mt5.equity = 990.0
    mt5.open_positions = [SimpleNamespace(symbol="EURUSD", type=0, volume=0.1, price_open=1.1, sl=1.09, tp=1.12,
                                          magic=7, ticket=1, profit=-4.0),
                          SimpleNamespace(symbol="GBPUSD", type=1, volume=0.1, price_open=1.3, sl=1.31, tp=1.28,
                                          magic=99, ticket=2, profit=50.0)]
    mt5.deals = [SimpleNamespace(magic=7, profit=-10.0, commission=-0.7, swap=0.0),
                 SimpleNamespace(magic=99, profit=100.0, commission=0.0, swap=0.0)]
    state = _broker(mt5).account()
    assert isinstance(state, AccountState)
    assert state.equity == 990.0
    assert state.open_positions == [("EURUSD", "BUY")]
    assert state.day_pnl == pytest.approx(-14.7)
    # l'altro caso legacy (senza MT5 -> saldo configurato) passa al broker simulato in P3.25
