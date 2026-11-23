"""Radice di composizione: dalla configurazione validata alle porte concrete (D-001).

Default sicuri: broker simulato con il capitale ACCOUNT_BALANCE, nessuna notizia, LLM locali via Ollama.
Il broker MT5 si costruisce solo tramite ports.build_broker, cioè solo con il doppio consenso; il suo
costruttore lo ricontrolla comunque. Il modulo MetaTrader5 arriva da fuori (main.py), mai importato qui.
"""
import json
import logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from adapters.finnhub_news import FinnhubNews
from adapters.news_cache import CachedNews
from adapters.llm_openai import OpenAiLlm, build_client
from adapters.mt5_broker import Mt5Broker
from adapters.mt5_data import Mt5Data
from adapters.null_news import NullNews, StaticNews
from adapters.sim_broker import SimBroker
from adapters.sqlite_store import SqliteStore
from app.config import Settings
from app.resolve import reconcile_broker, resolve_pending
from app.run_once import Ports, broker_from_settings, run_once

log = logging.getLogger(__name__)


def mt5_init_kwargs(cfg: Settings) -> dict:
    """Argomenti per mt5.initialize dal .env; vuoto senza credenziali (si usa il login del terminale)."""
    kwargs = {}
    if cfg.mt5_path:
        kwargs["path"] = cfg.mt5_path
    if cfg.mt5_login:
        kwargs["login"] = int(cfg.mt5_login)
        kwargs["password"] = cfg.mt5_password.get_secret_value()
        kwargs["server"] = cfg.mt5_server
    return kwargs


def ollama_digest(base_url: str, model: str, opener: Callable = urllib.request.urlopen) -> str:
    """Digest del modello da Ollama (/api/tags): identifica i pesi esatti dietro un nome come 'gemma3:12b'."""
    root = base_url.rstrip("/").removesuffix("/v1")
    with opener(urllib.request.Request(f"{root}/api/tags"), timeout=10) as resp:
        models = json.load(resp).get("models", [])
    for m in models:
        if m.get("name") == model or m.get("model") == model:
            return str(m["digest"])
    raise RuntimeError(f"modello {model!r} non presente in Ollama: eseguire 'ollama pull {model}'")


def _news(cfg: Settings):
    # D-015: le fonti live passano dalla cache, altrimenti la regola anti-futuro scarta ogni notizia
    cache = Path(cfg.db_path).parent / "news_cache.json"
    if cfg.news_provider == "finnhub":
        return CachedNews(FinnhubNews(cfg.finnhub_api_key), cache)
    if cfg.news_provider == "mock":
        return CachedNews(StaticNews(), cache)
    return NullNews()


def build_ports(cfg: Settings, mt5, digest_of: Optional[Callable[[str], str]] = None,
                clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Ports:
    digest_of = digest_of or (lambda model: ollama_digest(cfg.ollama_base_url, model))
    market = Mt5Data(mt5, clock)
    client = build_client(base_url=cfg.ollama_base_url, api_key="ollama", timeout_s=cfg.llm_timeout_seconds)

    def llm(model: str) -> OpenAiLlm:
        return OpenAiLlm(client, model=model, model_digest=digest_of(model), seed=cfg.llm_seed)

    Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(cfg.db_path, clock)
    broker = broker_from_settings(
        cfg,
        make_live=lambda: Mt5Broker(mt5, magic=cfg.magic_number, live_allowed=True, clock=clock),
        make_sim=lambda: SimBroker(quote=market.tick, equity=cfg.account_balance,
                                   commission_eur_per_lot=cfg.commission_eur_per_lot or 0.0,
                                   open_positions=store.open_sim_positions),  # D-016
    )
    log.info("composizione: broker %s, notizie %s, archivio %s",
             type(broker).__name__, cfg.news_provider, cfg.db_path)
    return Ports(market=market, news=_news(cfg), technical=llm(cfg.model_technical), macro=llm(cfg.model_macro),
                 store=store, broker=broker)


def make_cycle(cfg: Settings, ports: Ports, code_version: str,
               clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Callable[[datetime], None]:
    """Il lavoro di una candela: run_once per ogni simbolo (ognuno archivia i propri errori),
    poi la risoluzione virtuale dei candidati in attesa."""
    def cycle(candle_close: datetime) -> None:
        for symbol in cfg.symbols:
            run_once(symbol, candle_close, ports, cfg, code_version)
        try:
            resolve_pending(ports.store, ports.market, clock(), horizon=cfg.horizon_bars)
        except Exception:  # si riprova alla candela successiva: gli esiti non scadono
            log.exception("risoluzione virtuale fallita")
        try:
            reconcile_broker(ports.store, ports.broker, ports.market)
        except Exception:
            log.exception("riconciliazione con il broker fallita")
    return cycle
