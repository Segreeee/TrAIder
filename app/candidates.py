"""Generatore di candidati baseline, senza LLM: è la variante di controllo (D-003).

Regola: BUY se chiusura > EMA20 su M15 e chiusura > EMA50 su H1; SELL se entrambe sotto; altrimenti nessuno.
Ingresso al prezzo di esecuzione atteso: ask (= bid + spread) per i BUY, bid per i SELL. Le barre MT5 sono bid.
SL = 1.0·ATR, TP = 1.5·ATR, quindi p0 = 0.4.
"""
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pandas_ta as ta

from app.features import add_indicators, technical_features
from domain.pip import pip_size
from domain.types import Candidate, Direction

M15, H1 = timedelta(minutes=15), timedelta(hours=1)


def _closed_by(bars: pd.DataFrame, tf: timedelta, close: datetime) -> pd.DataFrame:
    """Solo barre chiuse entro `close`: le successive non esistevano al momento della decisione."""
    return bars[bars["timestamp"] + tf <= close].reset_index(drop=True)


def generate(
    symbol: str, bars: pd.DataFrame, htf: pd.DataFrame, candle_close: datetime,
    sl_atr: float = 1.0, tp_atr: float = 1.5, htf_ema: int = 50,
) -> Optional[tuple[Candidate, dict[str, float]]]:
    m15 = add_indicators(_closed_by(bars, M15, candle_close))
    h1 = _closed_by(htf, H1, candle_close)
    if m15.empty or len(h1) < htf_ema:
        return None
    last = m15.iloc[-1]
    ema_series = ta.ema(h1["close"], length=htf_ema)
    h1_ema = ema_series.iloc[-1] if ema_series is not None else float("nan")
    if pd.isna(last["atr"]) or pd.isna(last["ema_20"]) or pd.isna(last["rsi"]) or pd.isna(last["macd_hist"]) \
            or pd.isna(h1_ema) or last["atr"] <= 0:
        return None

    up = last["close"] > last["ema_20"] and h1["close"].iloc[-1] > h1_ema
    down = last["close"] < last["ema_20"] and h1["close"].iloc[-1] < h1_ema
    if not (up or down):
        return None

    point = pip_size(symbol) / 10  # prezzi a 5/3 cifre: lo spread MT5 è in punti
    atr = float(last["atr"])
    if up:
        entry = float(last["close"]) + float(last["spread"]) * point
        cand = Candidate(symbol, Direction.BUY, entry, entry - sl_atr * atr, entry + tp_atr * atr, candle_close)
    else:
        entry = float(last["close"])
        cand = Candidate(symbol, Direction.SELL, entry, entry + sl_atr * atr, entry - tp_atr * atr, candle_close)
    return cand, technical_features(last, 1 if up else -1)
