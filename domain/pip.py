"""Valore del pip per coppia forex, conto in EUR.

1 lotto standard = 100 000 unità della valuta base. Un pip vale pip_size * 100 000 unità
della valuta quotata; in EUR si divide per il cambio EUR/quotata (preso da conversion_symbol).
"""
from typing import Optional

CONTRACT_SIZE = 100_000
ACCOUNT_CCY = "EUR"


def _pair(symbol: str) -> str:
    """Primi 6 caratteri in maiuscolo: ignora suffissi del broker come 'EURUSD.a'."""
    return symbol.upper()[:6]


def pip_size(symbol: str) -> float:
    return 0.01 if _pair(symbol)[3:] == "JPY" else 0.0001


def conversion_symbol(symbol: str) -> Optional[str]:
    """Coppia EURxxx da cui leggere il cambio della valuta quotata; None se la quotata è già EUR."""
    quote = _pair(symbol)[3:]
    return None if quote == ACCOUNT_CCY else ACCOUNT_CCY + quote


def pip_value_eur(symbol: str, eur_quote_rate: float, lots: float = 1.0) -> float:
    """Valore in EUR di 1 pip per `lots` lotti. eur_quote_rate = prezzo di conversion_symbol (1.0 se None)."""
    if eur_quote_rate <= 0:
        raise ValueError("eur_quote_rate deve essere positivo")
    return pip_size(symbol) * CONTRACT_SIZE * lots / eur_quote_rate
