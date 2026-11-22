"""Ora del server MT5 contro UTC.

MT5 restituisce il campo `time` delle barre come epoch nell'ora del server del broker, non in UTC.
L'apertura della barra in formazione cade nell'intervallo [adesso + scarto - tf, adesso + scarto],
quindi aggiungendo mezzo timeframe e arrotondando all'ora si ricava lo scarto.
Funziona per timeframe fino a 30 minuti (l'errore massimo resta sotto la mezz'ora).
"""
from datetime import datetime, timezone
from typing import Optional


def server_offset_hours(bar_open_epoch: int, utc_now: datetime, tf_minutes: int) -> Optional[int]:
    """Scarto in ore (server - UTC) dalla barra in formazione; None se la barra è vecchia (mercato chiuso)."""
    if utc_now.tzinfo is None:
        raise ValueError("utc_now deve avere un fuso orario")
    diff = bar_open_epoch - utc_now.timestamp() + tf_minutes * 30  # centro dell'intervallo possibile
    offset = round(diff / 3600)
    if not -12 <= offset <= 14 or abs(diff - offset * 3600) > tf_minutes * 30 + 60:
        return None
    return offset


def to_utc(server_epoch: int, offset_hours: int) -> datetime:
    """Converte un epoch nell'ora del server in un datetime UTC."""
    return datetime.fromtimestamp(server_epoch - offset_hours * 3600, tz=timezone.utc)
