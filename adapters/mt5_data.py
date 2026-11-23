"""Dati di mercato da MetaTrader5. Il modulo mt5 è iniettato (nei test FakeMt5): questo file
non importa MetaTrader5; lo fa solo la composizione all'avvio. Solo lettura, nessun ordine."""
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from domain.clock import server_offset_hours
from domain.pip import conversion_symbol

log = logging.getLogger(__name__)

# timeframe -> (costante MT5, minuti). server_offset_hours vale fino a 30 minuti: la sonda usa sempre M15.
_TIMEFRAMES = {"M15": ("TIMEFRAME_M15", 15), "H1": ("TIMEFRAME_H1", 60)}
COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "spread"]


class Mt5Data:
    def __init__(self, mt5, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._mt5, self._clock = mt5, clock
        self._offset: Optional[int] = None

    def _server_offset(self, symbol: str) -> int:
        """Ricalcolato a ogni chiamata dalla barra M15 in formazione; se il mercato è chiuso
        si usa l'ultimo noto, e senza un valore noto non si tira a indovinare."""
        probe = self._mt5.copy_rates_from_pos(symbol, self._mt5.TIMEFRAME_M15, 0, 1)
        offset = server_offset_hours(int(probe[0]["time"]), self._clock(), 15) if probe is not None and len(probe) else None
        if offset is not None:
            if self._offset is not None and offset != self._offset:
                log.warning("offset del server MT5 cambiato: %+d -> %+d ore", self._offset, offset)
            self._offset = offset
        if self._offset is None:
            raise RuntimeError("offset del server MT5 sconosciuto: mercato chiuso e nessun valore precedente")
        return self._offset

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if timeframe.upper() not in _TIMEFRAMES:
            raise ValueError(f"timeframe non supportato: {timeframe}")
        if not self._mt5.symbol_select(symbol, True):
            raise RuntimeError(f"simbolo non disponibile: {symbol}")
        offset = self._server_offset(symbol)
        const = getattr(self._mt5, _TIMEFRAMES[timeframe.upper()][0])
        rates = self._mt5.copy_rates_from_pos(symbol, const, 1, count)  # posizione 0 = candela in formazione
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"nessuna candela per {symbol} {timeframe}: {self._mt5.last_error()}")
        df = pd.DataFrame(rates).rename(columns={"tick_volume": "volume"})
        df["timestamp"] = pd.to_datetime(df["time"] - offset * 3600, unit="s", utc=True)
        return df[COLUMNS]

    def tick(self, symbol: str) -> tuple[float, float]:
        # Un simbolo fuori dal Market Watch (es. EURCAD per il pip di USDCAD) non ha tick finché non è selezionato.
        if not self._mt5.symbol_select(symbol, True):
            raise RuntimeError(f"simbolo non disponibile: {symbol}")
        t = self._mt5.symbol_info_tick(symbol)
        if t is None:
            raise RuntimeError(f"nessun tick per {symbol}: {self._mt5.last_error()}")
        # Appena selezionato, il simbolo può avere bid/ask a 0 finché non arriva la prima quotazione.
        if t.bid <= 0 or t.ask <= 0:
            raise RuntimeError(f"tick vuoto per {symbol} (bid={t.bid}, ask={t.ask}): quotazione non ancora arrivata")
        return float(t.bid), float(t.ask)

    def eur_quote_rate(self, symbol: str) -> float:
        """Cambio EUR/valuta quotata (prezzo medio) per domain.pip.pip_value_eur; 1.0 se la quotata è EUR."""
        conv = conversion_symbol(symbol)
        if conv is None:
            return 1.0
        bid, ask = self.tick(conv)
        return (bid + ask) / 2
