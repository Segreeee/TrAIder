"""P3.15: adattatore dati MT5 con il modulo mt5 iniettato. Solo candele chiuse, orari in UTC
ricalcolando l'offset del server a ogni chiamata, colonna spread conservata."""
from datetime import datetime, timedelta, timezone

import pytest

from adapters.mt5_data import Mt5Data
from ports import MarketData
from tests.contracts.market_data_contract import check_market_data
from tests.fakes import FakeMt5

NOW = datetime(2026, 3, 2, 12, 7, tzinfo=timezone.utc)


def _data(mt5):
    return Mt5Data(mt5, clock=lambda: NOW)


def test_mt5_data_honours_contract():
    check_market_data(_data(FakeMt5(NOW, offset_hours=2)), "EURUSD", "M15", 15, NOW)
    assert isinstance(_data(FakeMt5(NOW)), MarketData)


def test_fetch_skips_forming_candle():
    # Porting di ClosedCandlesTest: le barre del ciclo partono dalla posizione 1, mai dalla 0.
    # La sola lettura della posizione 0 ammessa è la sonda di 1 barra per l'offset del server.
    mt5 = FakeMt5(NOW)
    _data(mt5).closed_bars("EURUSD", "M15", 5)
    assert (1, 5) in mt5.rate_calls
    assert all(start == 1 or count == 1 for start, count in mt5.rate_calls)


@pytest.mark.parametrize("offset", [0, 2, 3, -5])
def test_timestamps_converted_with_offset(offset):
    df = _data(FakeMt5(NOW, offset_hours=offset)).closed_bars("EURUSD", "M15", 3)
    # ultima barra chiusa alle 12:07 UTC: apertura 11:45 UTC qualunque sia l'ora del server
    assert df["timestamp"].iloc[-1].to_pydatetime() == datetime(2026, 3, 2, 11, 45, tzinfo=timezone.utc)


def test_offset_recomputed_each_call():
    # cambio dell'ora legale tra due cicli: lo stesso adattatore si adegua
    mt5 = FakeMt5(NOW, offset_hours=2)
    data = _data(mt5)
    first = data.closed_bars("EURUSD", "M15", 3)["timestamp"].iloc[-1]
    mt5.offset = 3
    assert data.closed_bars("EURUSD", "M15", 3)["timestamp"].iloc[-1] == first


def test_market_closed_reuses_last_known_offset():
    mt5 = FakeMt5(NOW, offset_hours=2)
    data = _data(mt5)
    data.closed_bars("EURUSD", "M15", 3)
    mt5.market_open = False
    last = data.closed_bars("EURUSD", "M15", 3)["timestamp"].iloc[-1].to_pydatetime()
    assert last == datetime(2026, 2, 27, 11, 45, tzinfo=timezone.utc)  # 3 giorni prima, in UTC


def test_market_closed_without_known_offset_raises():
    with pytest.raises(RuntimeError, match="offset"):
        _data(FakeMt5(NOW, market_open=False)).closed_bars("EURUSD", "M15", 3)


def test_spread_column_kept():
    df = _data(FakeMt5(NOW)).closed_bars("EURUSD", "M15", 3)
    assert (df["spread"] == 7).all()


def test_unknown_timeframe_raises():
    with pytest.raises(ValueError):
        _data(FakeMt5(NOW)).closed_bars("EURUSD", "M7", 3)


def test_eur_quote_rate_uses_conversion_symbol():
    data = _data(FakeMt5(NOW))
    assert data.eur_quote_rate("USDJPY") == pytest.approx(160.010)   # EURJPY, prezzo medio
    assert data.eur_quote_rate("GBPUSD") == pytest.approx(1.10004)   # EURUSD
    assert data.eur_quote_rate("EURGBP") == pytest.approx(0.85005)   # quotata GBP -> EURGBP
    assert data.eur_quote_rate("GBPEUR") == 1.0                      # quotata già in EUR


def test_tick_returns_bid_ask():
    assert _data(FakeMt5(NOW)).tick("EURUSD") == (1.10000, 1.10008)
