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


def first_hit(action: str, tp: float, sl: float, future_df: pd.DataFrame) -> Optional[tuple[str, float, int]]:
    """(esito, prezzo, posizione della barra) del primo tra TP/SL toccato; SL se ambigui nella stessa
    candela (scelta prudente). None se nessuno dei due è toccato."""
    for i, (high, low) in enumerate(zip(future_df["high"], future_df["low"])):
        if action == "BUY":
            hit_sl, hit_tp = low <= sl, high >= tp
        else:  # SELL
            hit_sl, hit_tp = high >= sl, low <= tp
        if hit_sl:
            return "SL", sl, i
        if hit_tp:
            return "TP", tp, i
    return None


def simulate_outcome(action: str, tp: float, sl: float, future_df: pd.DataFrame) -> tuple[str, Optional[float]]:
    """Primo tra TP/SL toccato tra le candele successive, altrimenti TIMEOUT all'ultima chiusura."""
    hit = first_hit(action, tp, sl, future_df)
    if hit is not None:
        return hit[0], hit[1]
    if len(future_df) == 0:
        return "TIMEOUT", None
    return "TIMEOUT", float(future_df.iloc[-1]["close"])
