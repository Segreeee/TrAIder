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
from datetime import datetime, timedelta, timezone
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


class NullNewsFeed(NewsFeed):
    """Nessuna fonte di notizie: restituisce sempre una lista vuota (default sicuro)."""

    def get_latest_news(self, symbol: str, limit: int = 3) -> List[NewsItem]:
        return []


def build_news_feed(provider: str, dry_run: bool) -> NewsFeed:
    """
    Sceglie la sorgente di notizie da NEWS_PROVIDER.

    - "none" (default): nessuna notizia. L'analista macro viene escluso.
    - "mock": notizie statiche inventate, SOLO in DRY_RUN. Con ordini reali
      sono vietate: sono sempre le stesse e sempre a favore dell'euro, quindi
      spingerebbero il modello verso operazioni senza alcun fondamento.
    """
    name = (provider or "none").strip().lower()
    if name == "none":
        return NullNewsFeed()
    if name == "mock":
        if not dry_run:
            raise ValueError(
                "NEWS_PROVIDER=mock non e' consentito con DRY_RUN=false: le notizie finte "
                "non possono guidare ordini reali."
            )
        logger.warning("Notizie MOCK attive: solo per prove in DRY_RUN.")
        return MockNewsFeed()
    raise ValueError(f"NEWS_PROVIDER sconosciuto: {provider!r} (valori ammessi: none, mock)")


class MockNewsFeed(NewsFeed):
    """
    Implementazione mock-up: restituisce notizie finanziarie statiche/plausibili.
    Da sostituire in produzione con una chiamata reale a Finnhub (news API),
    mantenendo la stessa firma `get_latest_news`.
    """

    def get_latest_news(self, symbol: str, limit: int = 3) -> List[NewsItem]:
        now = datetime.now(timezone.utc)
        mock_pool: List[NewsItem] = [
            {
                "headline": "ECB officials signal caution on further rate cuts amid sticky inflation",
                "source": "Reuters",
                "published_at": (now - timedelta(hours=2)).isoformat(),
                "summary": (
                    "Several ECB governing council members indicated the pace of easing "
                    "could slow if core inflation remains above target in the eurozone."
                ),
            },
            {
                "headline": "US Dollar weakens after softer-than-expected non-farm payrolls",
                "source": "Bloomberg",
                "published_at": (now - timedelta(hours=5)).isoformat(),
                "summary": (
                    "NFP data came in below consensus, fueling bets on a more dovish Fed "
                    "stance and pressuring the dollar against major peers."
                ),
            },
            {
                "headline": "Eurozone PMI beats expectations, signaling manufacturing recovery",
                "source": "Financial Times",
                "published_at": (now - timedelta(hours=9)).isoformat(),
                "summary": (
                    "Composite PMI rose above the 50 expansion threshold for the first time "
                    "in six months, driven by stronger German industrial output."
                ),
            },
        ]
        logger.debug("MockNewsFeed: restituite %d notizie per %s", limit, symbol)
        return mock_pool[:limit]


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
