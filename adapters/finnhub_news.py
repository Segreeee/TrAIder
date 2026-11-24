"""Notizie forex da Finnhub (D-005), solo per uso privato (T-008): i titoli restano in data/,
in pubblico solo metriche aggregate.

API: GET /api/v1/news?category=forex con la chiave nell'header X-Finnhub-Token (mai nell'URL).
published_at = campo UNIX `datetime` in UTC; fetched_at = orologio al momento della lettura,
che è ciò su cui si basa la regola anti-futuro (domain.news.visible_news).
Un errore di rete o una risposta non valida restituisce una lista vuota: il macro resta escluso
per quel ciclo, il ciclo continua.
"""
import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Callable

from pydantic import SecretStr

from domain.news import NewsItem

log = logging.getLogger(__name__)
URL = "https://finnhub.io/api/v1/news?category=forex"


class FinnhubNews:
    def __init__(self, api_key: SecretStr, opener: Callable = urllib.request.urlopen,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), timeout_s: float = 10.0):
        self._key, self._opener, self._clock, self._timeout = api_key, opener, clock, timeout_s

    def _redact(self, text: str) -> str:
        return text.replace(self._key.get_secret_value(), "***")

    def latest(self, symbol: str, limit: int) -> list[NewsItem]:
        # ponytail: notizie forex generali, non filtrate per coppia; filtro per valuta se il macro ne ha bisogno
        request = urllib.request.Request(URL, headers={"X-Finnhub-Token": self._key.get_secret_value()})
        try:
            with self._opener(request, timeout=self._timeout) as resp:
                data = json.load(resp)
        except (OSError, ValueError) as exc:  # URLError/HTTPError/timeout sono OSError; JSON rotto è ValueError
            log.warning("Finnhub non disponibile: %s", self._redact(f"{type(exc).__name__}: {exc}"))
            return []
        if not isinstance(data, list):
            log.warning("Finnhub: risposta inattesa (%s)", type(data).__name__)
            return []

        fetched = self._clock()
        items = []
        for d in data:
            try:
                published = datetime.fromtimestamp(int(d["datetime"]), tz=timezone.utc)
                headline = str(d["headline"]).strip()
            except (KeyError, TypeError, ValueError):
                continue
            if headline:
                items.append(NewsItem(headline, str(d.get("source") or "finnhub"), published, fetched))
        return sorted(items, key=lambda n: n.published_at, reverse=True)[:limit]
