"""Adattatori finti delle porte: deterministici, senza rete né MT5. Usati da contratti e test d'integrazione."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ports import CandidateRecord, LlmResponse, NewsItem, Outcome


class FakeMt5:
    """Sostituto del modulo MetaTrader5: barre nell'ORA DEL SERVER (UTC + offset_hours), come il vero MT5.
    Registra ogni chiamata a copy_rates_from_pos come (start, count)."""
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385

    _TF_SECONDS = {15: 900, 16385: 3600}

    def __init__(self, now: datetime, offset_hours: int = 2, ticks: dict | None = None, market_open: bool = True):
        self.now, self.offset, self.market_open = now, offset_hours, market_open
        self.ticks = ticks or {"EURUSD": (1.10000, 1.10008), "EURJPY": (160.000, 160.020), "EURGBP": (0.85000, 0.85010)}
        self.rate_calls: list[tuple[int, int]] = []

    def symbol_select(self, symbol, enable):
        return True

    def copy_rates_from_pos(self, symbol, tf, start, count):
        self.rate_calls.append((start, count))
        step = self._TF_SECONDS[tf]
        server_now = int(self.now.timestamp()) + self.offset * 3600
        if not self.market_open:
            server_now -= 3 * 86400  # ultima barra di venerdì: vecchia rispetto ad adesso
        forming = server_now // step * step
        opens = forming - step * (start + np.arange(count)[::-1])
        rng = np.random.default_rng(len(self.rate_calls))
        close = 1.10 + np.cumsum(rng.normal(0, 0.0005, count))
        dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
                 ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")]
        rows = [(int(t), c, c + 0.0004, c - 0.0004, c, 100, 7, 0) for t, c in zip(opens, close)]
        return np.array(rows, dtype=dtype)

    def symbol_info_tick(self, symbol):
        bid, ask = self.ticks[symbol]
        return type("Tick", (), {"bid": bid, "ask": ask, "time": int(self.now.timestamp())})()

    def last_error(self):
        return (0, "ok")


class FakeLlm:
    """Risposte scriptate in ordine; un'eccezione nello script simula un errore di trasporto."""

    def __init__(self, script: list, model: str = "fake-llm", digest: str = "sha256:fake", tokens=(10, 5)):
        self.script, self.model, self.model_digest, self.tokens = list(script), model, digest, tokens
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, *, temperature: float) -> LlmResponse:
        self.calls.append({"system": system, "user": user, "temperature": temperature})
        item = self.script.pop(0) if self.script else '{"ping": 1}'
        if isinstance(item, Exception):
            raise item
        return LlmResponse(text=item, tokens_in=self.tokens[0], tokens_out=self.tokens[1])


class FakeMarketData:
    """Cammino casuale con seme fisso; restituisce solo candele chiuse rispetto a `now`
    (salvo include_forming=True, usato per provare che il contratto la rifiuta)."""

    def __init__(self, now: datetime, tf_minutes: int, seed: int = 1, include_forming: bool = False):
        self.now, self.tf, self.seed, self.include_forming = now, tf_minutes, seed, include_forming

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        tf = timedelta(minutes=self.tf)
        epoch = datetime(1970, 1, 1, tzinfo=self.now.tzinfo)
        forming_open = epoch + ((self.now - epoch) // tf) * tf
        last_open = forming_open if self.include_forming else forming_open - tf
        ts = pd.date_range(end=last_open, periods=count, freq=tf, tz="UTC")

        rng = np.random.default_rng(self.seed)
        close = 1.10 + np.cumsum(rng.normal(0, 0.0005, count))
        open_ = np.r_[close[0], close[:-1]]
        wick = np.abs(rng.normal(0, 0.0003, (2, count)))
        return pd.DataFrame({
            "timestamp": ts,
            "open": open_,
            "high": np.maximum(open_, close) + wick[0],
            "low": np.minimum(open_, close) - wick[1],
            "close": close,
            "volume": rng.integers(50, 500, count),
            "spread": np.full(count, 8),  # punti: 0.8 pip a 5 cifre
        })


class FakeNews:
    def __init__(self, now: datetime, items: list[NewsItem] | None = None):
        self.items = items if items is not None else [
            NewsItem("BCE lascia i tassi invariati", "fake", now - timedelta(hours=3), now - timedelta(hours=2)),
            NewsItem("Dati sull'occupazione USA sopra le attese", "fake", now - timedelta(hours=1), now - timedelta(minutes=30)),
        ]

    def latest(self, symbol: str, limit: int) -> list[NewsItem]:
        return sorted(self.items, key=lambda n: n.published_at, reverse=True)[:limit]


class FakeStore:
    """Archivio in memoria con gli stessi vincoli di unicità dello schema SQLite (D-007)."""

    def __init__(self):
        self.cycles: dict[int, tuple[str, datetime]] = {}
        self.llm_calls: list[tuple] = []
        self.candidates: dict[int, tuple[int, CandidateRecord]] = {}
        self.executions: list[tuple] = []
        self.outcomes: dict[int, Outcome] = {}

    def begin_cycle(self, symbol: str, candle_close_utc: datetime) -> int | None:
        if (symbol, candle_close_utc) in self.cycles.values():
            return None
        cycle_id = len(self.cycles) + 1
        self.cycles[cycle_id] = (symbol, candle_close_utc)
        return cycle_id

    def last_cycle(self, symbol: str) -> datetime | None:
        return max((c for s, c in self.cycles.values() if s == symbol), default=None)

    def record_llm_call(self, cycle_id: int, role: str, result) -> None:
        self.llm_calls.append((cycle_id, role, result))

    def record_candidate(self, cycle_id: int, record: CandidateRecord) -> int:
        if any(c == cycle_id and r.variant == record.variant for c, r in self.candidates.values()):
            raise ValueError(f"candidato già registrato per la variante {record.variant}")
        cid = len(self.candidates) + 1
        self.candidates[cid] = (cycle_id, record)
        return cid

    def record_execution(self, candidate_id: int, fill, lots: float) -> None:
        self.executions.append((candidate_id, fill, lots))

    def record_outcome(self, candidate_id: int, outcome: Outcome) -> bool:
        if candidate_id in self.outcomes:
            return False
        self.outcomes[candidate_id] = outcome
        return True

    def pending_candidates(self) -> list[tuple[int, CandidateRecord]]:
        return [(cid, r) for cid, (_, r) in self.candidates.items() if cid not in self.outcomes]