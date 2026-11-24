"""Generatore di candidati baseline, senza LLM: è la variante di controllo (D-003).

Regola: BUY se chiusura > EMA20 su M15 e trend H1 rialzista (chiusura > EMA50); SELL se entrambi al ribasso.
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


def closed_by(bars: pd.DataFrame, tf: timedelta, close: datetime) -> pd.DataFrame:
    """Solo barre chiuse entro `close`: le successive non esistevano al momento della decisione."""
    return bars[bars["timestamp"] + tf <= close].reset_index(drop=True)


def htf_trend(htf: pd.DataFrame, candle_close: datetime, htf_ema: int = 50) -> str:
    """Trend H1 alla chiusura: chiusura vs EMA50 sulle sole barre H1 già chiuse."""
    h1 = closed_by(htf, H1, candle_close)
    ema = ta.ema(h1["close"], length=htf_ema) if len(h1) >= htf_ema else None
    if ema is None or pd.isna(ema.iloc[-1]):
        return "indeterminato"
    last = h1["close"].iloc[-1]
    return "rialzista" if last > ema.iloc[-1] else "ribassista" if last < ema.iloc[-1] else "laterale"


def generate(
    symbol: str, bars: pd.DataFrame, htf: pd.DataFrame, candle_close: datetime,
    sl_atr: float = 1.0, tp_atr: float = 1.5,
) -> Optional[tuple[Candidate, dict[str, float]]]:
    m15 = add_indicators(closed_by(bars, M15, candle_close))
    if m15.empty:
        return None
    last = m15.iloc[-1]
    if last[["atr", "ema_20", "rsi", "macd_hist"]].isna().any() or last["atr"] <= 0:
        return None

    trend = htf_trend(htf, candle_close)
    up = last["close"] > last["ema_20"] and trend == "rialzista"
    down = last["close"] < last["ema_20"] and trend == "ribassista"
    if not (up or down):
        return None

    point = pip_size(symbol) / 10  # prezzi a 5/3 cifre: lo spread MT5 è in punti
    atr = float(last["atr"])
    if round(min(sl_atr, tp_atr) * atr / pip_size(symbol), 1) == 0:
        return None  # volatilità quasi nulla: stop o target a meno di 0.1 pip, nessun candidato (R10)
    if up:
        entry = float(last["close"]) + float(last["spread"]) * point
        cand = Candidate(symbol, Direction.BUY, entry, entry - sl_atr * atr, entry + tp_atr * atr, candle_close)
    else:
        entry = float(last["close"])
        cand = Candidate(symbol, Direction.SELL, entry, entry + sl_atr * atr, entry - tp_atr * atr, candle_close)
    return cand, technical_features(last, 1 if up else -1)
