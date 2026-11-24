"""Dimensione del lotto con rischio massimo per operazione, costo incluso.

Rischio di un'operazione = lotti * (d_SL + costo) in pip * valore del pip in EUR per lotto.
Se anche il lotto minimo supererebbe il rischio massimo, il trade non si fa (lotto 0).
"""
import math


def lot_size(
    equity: float, risk_pct: float, d_sl_pips: float, cost_pips: float, pip_value_eur_per_lot: float,
    min_lot: float, lot_step: float, max_lot: float,
) -> float:
    if equity <= 0:
        raise ValueError("equity deve essere positiva")
    if not 0 < risk_pct <= 100:
        raise ValueError("risk_pct deve essere in (0, 100]")
    risk_per_lot = (d_sl_pips + cost_pips) * pip_value_eur_per_lot
    if d_sl_pips <= 0 or risk_per_lot <= 0:
        return 0.0
    raw = equity * risk_pct / 100 / risk_per_lot
    # Per difetto al passo; round(…, 9) evita che 0.55/0.01 = 54.999… perda un passo.
    stepped = math.floor(round(raw / lot_step, 9)) * lot_step
    if stepped < min_lot:
        return 0.0
    return round(min(stepped, max_lot), 8)
