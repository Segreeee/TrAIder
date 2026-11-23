"""Cache delle notizie live (D-015). Le fonti live scrivono fetched_at al momento della lettura, che nel
ciclo arriva sempre dopo la chiusura della candela: la regola anti-futuro (domain.news.visible_news) le
scarterebbe tutte. latest() restituisce solo ciò che era già noto prima di questa lettura, con il suo
fetched_at originale, poi aggiorna la cache: notizie con una candela di ritardo, regola intatta.

Con `path` la cache sopravvive ai riavvii (python main.py --once è un processo nuovo a ogni avvio).
Titoli solo in data/, per uso privato (T-008).
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from domain.news import NewsItem
from ports import NewsFeed

log = logging.getLogger(__name__)
KEEP = 100  # notizie per simbolo tenute in cache, le più recenti per published_at


def _newest(items: list[NewsItem]) -> list[NewsItem]:
    return sorted(items, key=lambda n: n.published_at, reverse=True)


class CachedNews:
    def __init__(self, inner: NewsFeed, path: Optional[Path] = None):
        self.inner, self._path = inner, path
        self._cache: dict[str, list[NewsItem]] = self._load()

    def latest(self, symbol: str, limit: int) -> list[NewsItem]:
        known = self._cache.get(symbol, [])
        seen = {(n.headline, n.published_at) for n in known}
        fresh = [n for n in self.inner.latest(symbol, KEEP) if (n.headline, n.published_at) not in seen]
        self._cache[symbol] = _newest(known + fresh)[:KEEP]
        self._save()
        return _newest(known)[:limit]

    def _load(self) -> dict[str, list[NewsItem]]:
        if self._path is None or not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return {s: [NewsItem(d["headline"], d["source"], datetime.fromisoformat(d["published_at"]),
                                 datetime.fromisoformat(d["fetched_at"])) for d in items] for s, items in raw.items()}
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            log.warning("cache delle notizie illeggibile (%s): riparto vuoto", type(exc).__name__)
            return {}

    def _save(self) -> None:
        if self._path is None:
            return
        data = {s: [{"headline": n.headline, "source": n.source, "published_at": n.published_at.isoformat(),
                     "fetched_at": n.fetched_at.isoformat()} for n in items] for s, items in self._cache.items()}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)  # scrittura atomica: un'interruzione non lascia un file a metà
