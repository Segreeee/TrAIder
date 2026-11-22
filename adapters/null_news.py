"""Fonti di notizie senza rete: nessuna notizia (default, NEWS_PROVIDER=none) e notizie fisse per le prove
(NEWS_PROVIDER=mock, ammesso solo in DRY_RUN da app.config)."""
from datetime import datetime, timedelta, timezone
from typing import Callable

from domain.news import NewsItem


class NullNews:
    def latest(self, symbol: str, limit: int) -> list[NewsItem]:
        return []


class StaticNews:
    """Due titoli inventati, scaricati "adesso": servono solo a provare il percorso del macro."""

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._clock = clock

    def latest(self, symbol: str, limit: int) -> list[NewsItem]:
        now = self._clock()
        return [NewsItem("[PROVA] Banca centrale lascia i tassi invariati", "mock", now - timedelta(hours=2), now),
                NewsItem("[PROVA] Dati sull'occupazione sopra le attese", "mock", now - timedelta(hours=1), now)][:limit]
