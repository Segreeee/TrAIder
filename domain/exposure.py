"""
Controlli di portafoglio prima di aprire una nuova posizione.

Funzioni pure (nessuna dipendenza da MT5) cosi' da poterle testare:
- una sola posizione per simbolo,
- numero massimo di posizioni aperte,
- esposizione massima per singola valuta: comprare EURUSD e GBPUSD insieme
  e' la stessa scommessa contro il dollaro, quindi conta doppio sull'USD,
- limite di perdita giornaliero.
"""
from typing import Iterable


def split_symbol(symbol: str) -> tuple[str, str]:
    """'EURUSD' -> ('EUR', 'USD'). Ignora eventuali suffissi del broker (es. 'EURUSD.a')."""
    s = symbol.upper()
    return s[:3], s[3:6]


def currency_exposure(positions: Iterable[tuple[str, str]]) -> dict[str, int]:
    """
    Esposizione netta per valuta in "numero di posizioni": BUY EURUSD = EUR +1, USD -1.
    Ogni posizione conta 1 a prescindere dal lotto: e' un limite di concentrazione,
    non una misura di rischio in euro.
    """
    exposure: dict[str, int] = {}
    for symbol, action in positions:
        base, quote = split_symbol(symbol)
        sign = 1 if action == "BUY" else -1
        exposure[base] = exposure.get(base, 0) + sign
        exposure[quote] = exposure.get(quote, 0) - sign
    return exposure


def check_new_position(
    symbol: str,
    action: str,
    open_positions: list[tuple[str, str]],
    max_open_positions: int,
    max_currency_exposure: int,
) -> tuple[bool, str]:
    """(consentito, motivo). Il motivo e' vuoto se la posizione e' consentita."""
    if any(s.upper() == symbol.upper() for s, _ in open_positions):
        return False, f"posizione gia' aperta su {symbol.upper()}"
    if len(open_positions) >= max_open_positions:
        return False, f"raggiunto il massimo di {max_open_positions} posizioni aperte"

    before = currency_exposure(open_positions)
    after = currency_exposure(open_positions + [(symbol, action)])
    for currency, value in after.items():
        if abs(value) > max_currency_exposure and abs(value) > abs(before.get(currency, 0)):
            return False, (
                f"esposizione su {currency} salirebbe a {value:+d} posizioni "
                f"(massimo {max_currency_exposure})"
            )
    return True, ""


def daily_loss_limit_reached(day_pnl: float, equity: float, limit_pct: float) -> bool:
    """
    Vero se la perdita del giorno (realizzata + aperta) ha raggiunto `limit_pct`
    del capitale di inizio giornata (equity attuale - risultato del giorno).
    """
    if day_pnl >= 0 or limit_pct <= 0:
        return False
    start_equity = equity - day_pnl
    if start_equity <= 0:
        return True
    return -day_pnl / start_equity * 100 >= limit_pct - 1e-9
