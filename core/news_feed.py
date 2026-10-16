"""
Data Ingestion (Notizie) - modulo mock-up.

Espone la stessa interfaccia che avra' in futuro l'integrazione reale
(es. Finnhub News API), cosi' da poter sostituire `MockNewsFeed` con
`FinnhubNewsFeed` senza toccare il resto della pipeline.
"""
import logging
from datetime import datetime, timedelta, timezone
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
