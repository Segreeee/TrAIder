"""Porte verso il mondo esterno (D-001). Il dominio non le conosce; l'orchestrazione le riceve
già costruite. Ogni porta ha un fake in tests/fakes.py e un contratto in tests/contracts/.
Le porte LLM, Broker e SignalStore arrivano nei passi P3.12–P3.14."""
from typing import Protocol, runtime_checkable

import pandas as pd

from domain.news import NewsItem

__all__ = ["MarketData", "NewsFeed", "NewsItem"]


@runtime_checkable
class MarketData(Protocol):
    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Ultime `count` candele chiuse. Colonne: timestamp (apertura, UTC tz-aware),
        open, high, low, close, volume, spread (in punti)."""
        ...


@runtime_checkable
class NewsFeed(Protocol):
    def latest(self, symbol: str, limit: int) -> list[NewsItem]:
        """Notizie più recenti per il simbolo, con published_at e fetched_at tz-aware."""
        ...
