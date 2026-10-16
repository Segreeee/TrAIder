"""
Data Ingestion (Notizie).

`NewsFeed` e' l'interfaccia; `YahooNewsFeed` e' l'implementazione reale (RSS
pubblico). Una sorgente diversa (es. Finnhub) si aggiunge implementando
`get_latest_news` senza toccare il resto della pipeline.
"""
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import List, TypedDict

logger = logging.getLogger(__name__)


class NewsItem(TypedDict):
    headline: str
    source: str
    published_at: str
    summary: str


class NewsFeed:
    """Interfaccia astratta per una sorgente di notizie finanziarie."""

    def get_latest_news(self, symbol: str, limit: int = 3) -> List[NewsItem]:
        raise NotImplementedError


class YahooNewsFeed(NewsFeed):
    """
    Notizie reali dal feed RSS pubblico di Yahoo Finance per il simbolo (nessuna
    chiave API). Se il feed non risponde restituisce una lista vuota: mai notizie
    inventate, il prompt mostrera' "Nessuna notizia rilevante disponibile".
    """

    URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"

    @staticmethod
    def _ticker(symbol: str) -> str:
        # Yahoo quota le coppie USDxxx come "xxx=X" (USDJPY -> JPY=X), le altre come "EURUSD=X".
        return f"{symbol[3:]}=X" if symbol.startswith("USD") else f"{symbol}=X"

    def get_latest_news(self, symbol: str, limit: int = 3) -> List[NewsItem]:
        try:
            req = urllib.request.Request(
                self.URL.format(ticker=self._ticker(symbol)), headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                root = ET.fromstring(resp.read())
        except (OSError, ET.ParseError) as exc:
            logger.warning("Notizie non disponibili per %s: %s", symbol, exc)
            return []

        items: List[NewsItem] = []
        for node in root.iter("item"):
            try:
                published = parsedate_to_datetime(node.findtext("pubDate", "")).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError):
                published = ""
            items.append({
                "headline": (node.findtext("title") or "").strip(),
                "source": (node.findtext("source") or "Yahoo Finance").strip(),
                "published_at": published,
                "summary": re.sub(r"<[^>]+>", "", node.findtext("description") or "").strip(),
            })
        items.sort(key=lambda n: n["published_at"], reverse=True)
        return items[:limit]
