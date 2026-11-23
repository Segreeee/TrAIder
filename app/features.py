"""Indicatori tecnici e caratteristiche numeriche per il modello di probabilità (Fase 4)."""
import numpy as np
import pandas as pd
import pandas_ta as ta


def add_indicators(
    df: pd.DataFrame, rsi_length: int = 14, ema_length: int = 20,
    macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9,
    atr_length: int = 14, bb_length: int = 20, bb_std: float = 2.0,
) -> pd.DataFrame:
    """Aggiunge RSI, EMA, MACD, ATR e Bollinger. Le colonne multi-output si leggono per posizione:
    pandas-ta cambia le etichette tra versioni."""
    out = df.copy()

    def cols(result, n):
        # con poche barre pandas-ta restituisce None invece di NaN: si normalizza a NaN
        if result is None:
            return [np.nan] * n
        frame = result.to_frame() if isinstance(result, pd.Series) else result
        return [frame.iloc[:, i] for i in range(n)]

    out["rsi"], = cols(ta.rsi(out["close"], length=rsi_length), 1)
    out["ema_20"], = cols(ta.ema(out["close"], length=ema_length), 1)
    out["macd"], out["macd_hist"], out["macd_signal"] = cols(
        ta.macd(out["close"], fast=macd_fast, slow=macd_slow, signal=macd_signal), 3)
    out["atr"], = cols(ta.atr(out["high"], out["low"], out["close"], length=atr_length), 1)
    out["bb_lower"], out["bb_mid"], out["bb_upper"] = cols(ta.bbands(out["close"], length=bb_length, std=bb_std), 3)  # type: ignore[arg-type]  # stub di pandas_ta errato: std è un numero
    return out


def technical_features(row: pd.Series, sign: int) -> dict[str, float]:
    """Tre caratteristiche con il segno della direzione (+ = a favore), limitate a ±3.
    La standardizzazione sul passato la fa il fit walk-forward, non questo modulo."""
    atr = float(row["atr"])
    return {
        "momentum": float(np.clip((row["close"] - row["ema_20"]) / atr, -3, 3)) * sign,
        "rsi_dev": float((row["rsi"] - 50) / 50) * sign,
        "macd_hist_atr": float(np.clip(row["macd_hist"] / atr, -3, 3)) * sign,
    }
