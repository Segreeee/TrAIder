"""Dati di mercato da MetaTrader5. Il modulo mt5 è iniettato (nei test FakeMt5): questo file
non importa MetaTrader5; lo fa solo la composizione all'avvio. Solo lettura, nessun ordine."""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import pandas as pd

from domain.clock import NEW_YORK, NY_CLOSE_SHIFT_HOURS, ny_close_offset_hours, server_offset_hours
from domain.pip import conversion_symbol

log = logging.getLogger(__name__)

# timeframe -> (costante MT5, minuti). server_offset_hours vale fino a 30 minuti: la sonda usa sempre M15.
_TIMEFRAMES = {"M15": ("TIMEFRAME_M15", 15), "H1": ("TIMEFRAME_H1", 60)}
COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "spread"]
QUOTE_WAIT_S, QUOTE_TRIES = 0.1, 10   # attesa della prima quotazione dopo symbol_select: ~1 s in tutto
BAR_WAIT_S, BAR_TRIES = 1.0, 10       # attesa della barra nuova quando il primo tick tarda: ~10 s in tutto


class Mt5Data:
    def __init__(self, mt5, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 sleep: Callable[[float], None] = time.sleep):
        self._mt5, self._clock, self._sleep = mt5, clock, sleep
        self._offset: Optional[int] = None
        self._rule_warned = False

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
        df = self._read(symbol, timeframe.upper(), count)
        # Indietro di una sola barra: il primo tick della barra nuova non è ancora arrivato (pochi secondi dopo
        # la chiusura, rollover). Si attende un poco; più indietro di così è mercato chiuso e non si aspetta.
        for _ in range(BAR_TRIES):
            if not self._one_bar_late(df, _TIMEFRAMES[timeframe.upper()][1]):
                break
            self._sleep(BAR_WAIT_S)
            df = self._read(symbol, timeframe.upper(), count)
        return df

    def _one_bar_late(self, df: pd.DataFrame, tf_min: int) -> bool:
        if df.empty:
            return False
        step = timedelta(minutes=tf_min)
        now = self._clock()
        current_open = datetime.fromtimestamp(int(now.timestamp()) // (tf_min * 60) * tf_min * 60, timezone.utc)
        return bool(df["timestamp"].iloc[-1].to_pydatetime() == current_open - 2 * step)

    def _read(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        offset = self._server_offset(symbol)
        const = getattr(self._mt5, _TIMEFRAMES[timeframe][0])
        rates = self._mt5.copy_rates_from_pos(symbol, const, 1, count)  # posizione 0 = candela in formazione
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"nessuna candela per {symbol} {timeframe}: {self._mt5.last_error()}")
        df = pd.DataFrame(rates).rename(columns={"tick_volume": "volume"})
        df["timestamp"] = self._to_utc(df["time"], offset)
        if df["timestamp"].isna().any():  # ora ripetuta o saltata dal server: solo di domenica, mercato chiuso
            log.warning("%s: %d barre in un'ora ambigua del cambio d'ora, scartate", symbol, df["timestamp"].isna().sum())
            df = df[df["timestamp"].notna()].reset_index(drop=True)
        return df[COLUMNS]

    def _to_utc(self, server_epochs: pd.Series, offset: int) -> pd.Series:
        """T-011: se il server segue la regola "New York + 7" (l'offset misurato adesso coincide con quello della
        regola), ogni barra si converte con il suo offset, anche a cavallo del cambio d'ora; altrimenti tutte con
        l'offset di adesso, come prima, e un avviso una volta sola."""
        if offset == ny_close_offset_hours(self._clock()):
            ny_local = pd.to_datetime(server_epochs, unit="s") - pd.Timedelta(hours=NY_CLOSE_SHIFT_HOURS)
            return ny_local.dt.tz_localize(NEW_YORK.key, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        if not self._rule_warned:
            log.warning("offset del server %+d diverso dalla regola New York + 7: ogni barra usa l'offset di adesso "
                        "(barre a cavallo di un cambio d'ora sbagliate di un'ora, T-011)", offset)
            self._rule_warned = True
        return pd.to_datetime(server_epochs - offset * 3600, unit="s", utc=True)

    def tick(self, symbol: str) -> tuple[float, float]:
        # Un simbolo fuori dal Market Watch (es. EURCAD per il pip di USDCAD) non ha tick finché non è selezionato.
        if not self._mt5.symbol_select(symbol, True):
            raise RuntimeError(f"simbolo non disponibile: {symbol}")
        t = self._mt5.symbol_info_tick(symbol)
        # Appena selezionato, il simbolo può avere bid/ask a 0 finché non arriva la prima quotazione.
        for _ in range(QUOTE_TRIES):
            if t is None or (t.bid > 0 and t.ask > 0):
                break
            self._sleep(QUOTE_WAIT_S)
            t = self._mt5.symbol_info_tick(symbol)
        if t is None:
            raise RuntimeError(f"nessun tick per {symbol}: {self._mt5.last_error()}")
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
