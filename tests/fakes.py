"""Adattatori finti delle porte: deterministici, senza rete né MT5. Usati da contratti e test d'integrazione."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ports import LlmResponse, NewsItem


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
