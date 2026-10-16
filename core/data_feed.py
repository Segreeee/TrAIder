"""
Data Ingestion (Mercato).

Responsabilita':
- Aprire/gestire la connessione al terminale MetaTrader5.
- Scaricare le ultime N candele OHLCV per un simbolo/timeframe.
- Calcolare indicatori tecnici di base (RSI, EMA20) via pandas-ta.
- Esporre i dati in un formato compatto pronto per il prompt LLM.
"""
import logging
from typing import Optional

import pandas as pd
import pandas_ta as ta

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - MT5 e' disponibile solo su Windows
    mt5 = None

from config.settings import settings

logger = logging.getLogger(__name__)

# Mappa stringa -> costante timeframe MT5
_TIMEFRAME_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


class DataFeedError(Exception):
    """Errore nel recupero/preparazione dei dati di mercato."""


class MarketDataFeed:
    """Wrapper per l'estrazione e l'arricchimento dei dati OHLCV da MT5."""

    def __init__(self):
        self._connected = False

    # ------------------------------------------------------------------ #
    # Connessione
    # ------------------------------------------------------------------ #
    def connect(self) -> None:
        if mt5 is None:
            raise DataFeedError(
                "Il pacchetto 'MetaTrader5' non e' disponibile in questo ambiente "
                "(supportato solo su Windows con terminale MT5 installato)."
            )

        init_kwargs = {}
        if settings.mt5_path:
            init_kwargs["path"] = settings.mt5_path
        if settings.mt5_login:
            init_kwargs["login"] = int(settings.mt5_login)
            init_kwargs["password"] = settings.mt5_password
            init_kwargs["server"] = settings.mt5_server

        if not mt5.initialize(**init_kwargs):
            error = mt5.last_error()
            raise DataFeedError(f"Impossibile inizializzare MT5: {error}")

        self._connected = True
        logger.info("Connessione a MetaTrader5 stabilita.")

    def shutdown(self) -> None:
        if mt5 is not None and self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("Connessione a MetaTrader5 chiusa.")

    # ------------------------------------------------------------------ #
    # Estrazione dati
    # ------------------------------------------------------------------ #
    def fetch_ohlcv(
        self, symbol: Optional[str] = None, timeframe: Optional[str] = None, count: Optional[int] = None
    ) -> pd.DataFrame:
        """Scarica le ultime `count` candele per `symbol`/`timeframe` e restituisce un DataFrame OHLCV."""
        if not self._connected:
            raise DataFeedError("Chiamare connect() prima di fetch_ohlcv().")

        symbol = symbol or settings.symbol
        timeframe = timeframe or settings.timeframe
        count = count or settings.candles_count

        tf_attr = _TIMEFRAME_MAP.get(timeframe.upper())
        if tf_attr is None:
            raise DataFeedError(f"Timeframe non supportato: {timeframe}")
        tf_const = getattr(mt5, tf_attr)

        if not mt5.symbol_select(symbol, True):
            raise DataFeedError(f"Simbolo non disponibile/selezionabile: {symbol}")

        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, count)
        if rates is None or len(rates) == 0:
            raise DataFeedError(
                f"Nessuna candela ricevuta per {symbol} {timeframe}: {mt5.last_error()}"
            )
        return self._normalize_rates(rates)

    def fetch_ohlcv_range(
        self, symbol: str, timeframe: str, start, end,
    ) -> pd.DataFrame:
        """
        Scarica lo storico OHLCV di `symbol`/`timeframe` tra `start` ed `end`
        (datetime, interpretati in UTC come richiesto da MT5). Usato dal
        backtester per ottenere un range esteso, a differenza di `fetch_ohlcv`
        che prende solo le ultime N candele.
        """
        if not self._connected:
            raise DataFeedError("Chiamare connect() prima di fetch_ohlcv_range().")

        tf_attr = _TIMEFRAME_MAP.get(timeframe.upper())
        if tf_attr is None:
            raise DataFeedError(f"Timeframe non supportato: {timeframe}")
        tf_const = getattr(mt5, tf_attr)

        if not mt5.symbol_select(symbol, True):
            raise DataFeedError(f"Simbolo non disponibile/selezionabile: {symbol}")

        rates = mt5.copy_rates_range(symbol, tf_const, start, end)
        if rates is None or len(rates) == 0:
            raise DataFeedError(
                f"Nessuna candela storica ricevuta per {symbol} {timeframe} tra {start} e {end}: {mt5.last_error()}"
            )
        return self._normalize_rates(rates)

    @staticmethod
    def _normalize_rates(rates) -> pd.DataFrame:
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(
            columns={
                "time": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "tick_volume": "volume",
            }
        )
        return df[["timestamp", "open", "high", "low", "close", "volume"]]

    # ------------------------------------------------------------------ #
    # Indicatori
    # ------------------------------------------------------------------ #
    @staticmethod
    def add_indicators(
        df: pd.DataFrame, rsi_length: int = 14, ema_length: int = 20,
        macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9,
        atr_length: int = 14, bb_length: int = 20, bb_std: float = 2.0,
    ) -> pd.DataFrame:
        """Aggiunge RSI, EMA, MACD, ATR e Bollinger Bands al DataFrame OHLCV.

        Le colonne dei DataFrame multi-output (MACD, Bollinger) vengono lette
        per posizione (non per nome) perche' pandas-ta puo' cambiare le
        etichette esatte tra versioni/fork del pacchetto.
        """
        enriched = df.copy()
        enriched["rsi"] = ta.rsi(enriched["close"], length=rsi_length)
        enriched["ema_20"] = ta.ema(enriched["close"], length=ema_length)

        macd_df = ta.macd(enriched["close"], fast=macd_fast, slow=macd_slow, signal=macd_signal)
        enriched["macd"] = macd_df.iloc[:, 0]
        enriched["macd_hist"] = macd_df.iloc[:, 1]
        enriched["macd_signal"] = macd_df.iloc[:, 2]

        enriched["atr"] = ta.atr(enriched["high"], enriched["low"], enriched["close"], length=atr_length)

        bb_df = ta.bbands(enriched["close"], length=bb_length, std=bb_std)
        enriched["bb_lower"] = bb_df.iloc[:, 0]
        enriched["bb_mid"] = bb_df.iloc[:, 1]
        enriched["bb_upper"] = bb_df.iloc[:, 2]

        return enriched

    def get_higher_timeframe_trend(
        self, symbol: Optional[str] = None, timeframe: str = "H1", count: int = 100, ema_length: int = 50,
    ) -> dict:
        """
        Fornisce un contesto di trend su un timeframe superiore (default H1),
        cosi' che l'LLM possa valutare l'allineamento tra il timeframe operativo
        (M15) e il trend di fondo prima di decidere.
        """
        htf_df = self.fetch_ohlcv(symbol=symbol, timeframe=timeframe, count=count)
        ema = ta.ema(htf_df["close"], length=ema_length)
        last_close = float(htf_df["close"].iloc[-1])
        last_ema = float(ema.iloc[-1]) if not pd.isna(ema.iloc[-1]) else None

        if last_ema is None:
            trend = "indeterminato"
        elif last_close > last_ema:
            trend = "rialzista"
        elif last_close < last_ema:
            trend = "ribassista"
        else:
            trend = "laterale"

        return {
            "timeframe": timeframe,
            "last_close": round(last_close, 5),
            f"ema_{ema_length}": None if last_ema is None else round(last_ema, 5),
            "trend": trend,
        }

    # ------------------------------------------------------------------ #
    # Serializzazione compatta per il prompt LLM
    # ------------------------------------------------------------------ #
    @staticmethod
    def to_compact_payload(df: pd.DataFrame, last_n: int = 20) -> dict:
        """
        Riduce il DataFrame arricchito a un payload minimale per il prompt:
        - ultime `last_n` candele in formato lista di liste (ohlc) per risparmiare token
        - valori correnti degli indicatori (ultima riga)
        """
        tail = df.tail(last_n).copy()
        tail["timestamp"] = tail["timestamp"].astype(str)

        candles = tail[["timestamp", "open", "high", "low", "close", "volume"]].values.tolist()
        last_row = df.iloc[-1]

        def _val(col: str, decimals: int) -> Optional[float]:
            v = last_row.get(col)
            return None if v is None or pd.isna(v) else round(float(v), decimals)

        indicators = {
            "rsi_14": _val("rsi", 2),
            "ema_20": _val("ema_20", 5),
            "macd": _val("macd", 6),
            "macd_signal": _val("macd_signal", 6),
            "macd_hist": _val("macd_hist", 6),
            "atr_14": _val("atr", 5),
            "bb_upper": _val("bb_upper", 5),
            "bb_mid": _val("bb_mid", 5),
            "bb_lower": _val("bb_lower", 5),
            "last_close": round(float(last_row["close"]), 5),
        }

        return {"candles": candles, "indicators": indicators}
