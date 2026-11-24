"""Costi di un'operazione e distanze di prezzo, tutto in pip."""


def distance_pips(a: float, b: float, pip_size: float) -> float:
    """Distanza in pip arrotondata a 0.1 pip (precisione dei prezzi a 5/3 cifre).

    L'arrotondamento elimina il rumore della virgola mobile: senza, 30/20 pip danno 1.4999 (T-009).
    """
    return round(abs(a - b) / pip_size, 1)


def cost_pips(
    spread_points: float, point: float, pip_size: float,
    commission_eur_per_lot: float, pip_value_eur_per_lot: float, slippage_pips: float,
) -> float:
    """Costo andata e ritorno in pip: spread + commissione convertita in pip + slippage."""
    spread = spread_points * point / pip_size
    commission = commission_eur_per_lot / pip_value_eur_per_lot if commission_eur_per_lot else 0.0
    return spread + commission + slippage_pips
