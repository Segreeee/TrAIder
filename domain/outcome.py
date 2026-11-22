"""Esito di un candidato: simulazione TP/SL sulle barre successive e risultato in R, lordo e netto."""
from typing import Optional

import pandas as pd


def realized_result(
    action: str, entry_price: float, exit_price: float, stop_loss_price: float,
    pip_size: float, cost_pips: float,
) -> dict:
    """
    Risultato di un'operazione chiusa: pip netti, R netto e R lordo.
    Il costo (spread + commissioni + slippage, andata e ritorno) si sottrae
    sempre, sia sui guadagni sia sulle perdite. R e' misurato sulla distanza
    tra ingresso e stop.
    """
    realized = (exit_price - entry_price) if action == "BUY" else (entry_price - exit_price)
    cost = cost_pips * pip_size
    risk_distance = abs(entry_price - stop_loss_price)
    if risk_distance <= 0:
        return {"pips": round((realized - cost) / pip_size, 1), "r_multiple": None, "r_multiple_gross": None}
    return {
        "pips": round((realized - cost) / pip_size, 1),
        "r_multiple": round((realized - cost) / risk_distance, 3),
        "r_multiple_gross": round(realized / risk_distance, 3),
    }


def simulate_outcome(action: str, tp: float, sl: float, future_df: pd.DataFrame) -> tuple[str, Optional[float]]:
    """
    Cammina in avanti tra le candele successive: primo tra TP/SL toccato vince
    (SL se ambigui nella stessa candela, scelta prudente).
    """
    for _, row in future_df.iterrows():
        high, low = row["high"], row["low"]
        if action == "BUY":
            hit_sl, hit_tp = low <= sl, high >= tp
        else:  # SELL
            hit_sl, hit_tp = high >= sl, low <= tp
        if hit_sl:
            return "SL", sl
        if hit_tp:
            return "TP", tp
    if len(future_df) == 0:
        return "TIMEOUT", None
    return "TIMEOUT", float(future_df.iloc[-1]["close"])
