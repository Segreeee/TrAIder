"""Notizie e regola anti-futuro.

Una notizia entra nel ciclo di una candela solo se fetched_at ≤ chiusura E published_at ≤ chiusura:
fetched_at garantisce che l'avremmo avuta davvero in quel momento (anche in un backtest),
published_at protegge da fonti con orologio sfasato.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewsItem:
    headline: str
    source: str
    published_at: datetime
    fetched_at: datetime

    def __post_init__(self):
        if self.published_at.tzinfo is None or self.fetched_at.tzinfo is None:
            raise ValueError("published_at e fetched_at devono avere il fuso orario")


def visible_news(items: list[NewsItem], candle_close: datetime) -> list[NewsItem]:
    if candle_close.tzinfo is None:
        raise ValueError("candle_close deve avere il fuso orario")
    return [n for n in items if n.fetched_at <= candle_close and n.published_at <= candle_close]
