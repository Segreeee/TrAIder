"""Contratto della porta MarketData: lo stesso controllo gira sul fake e (P3.15) sull'adattatore MT5."""
from datetime import datetime, timedelta

import pandas as pd

COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "spread"]


def check_market_data(adapter, symbol: str, timeframe: str, tf_minutes: int, now: datetime, count: int = 50):
    df = adapter.closed_bars(symbol, timeframe, count)

    assert list(df.columns) == COLUMNS, f"colonne attese {COLUMNS}, trovate {list(df.columns)}"
    assert 0 < len(df) <= count

    ts = df["timestamp"]
    assert isinstance(ts.dtype, pd.DatetimeTZDtype) and str(ts.dt.tz) == "UTC", "timestamp in UTC tz-aware"
    assert ts.is_monotonic_increasing and ts.is_unique, "timestamp strettamente crescenti"

    # solo candele chiuse: apertura dell'ultima + durata ≤ adesso
    assert ts.iloc[-1].to_pydatetime() + timedelta(minutes=tf_minutes) <= now, "candela in formazione restituita"

    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    assert (df["spread"] >= 0).all()
