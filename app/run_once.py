"""Un ciclo per simbolo e candela chiusa: la Facade di D-001.

begin_cycle (idempotenza) → dati → candidato baseline → analisti LLM → finish_cycle con l'input completo.
La decisione (varianti, probabilità, gate, rischio) si aggiunge in P3.26.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

from app.candidates import M15, closed_by, generate, htf_trend
from app.config import Settings
from app.extractors import AnalystView, feature_from_result
from app.features import add_indicators
from app.prompts import MACRO_PROMPT_VERSION, TECHNICAL_PROMPT_VERSION, build_macro_prompt, build_technical_prompt
from domain.news import visible_news
from domain.types import Candidate
from ports import Llm, MarketData, NewsFeed, SignalStore, call_validated

log = logging.getLogger(__name__)
HTF_BARS, NEWS_LIMIT, SNAPSHOT_BARS = 120, 10, 20


@dataclass
class Ports:
    market: MarketData
    news: NewsFeed
    technical: Llm
    macro: Llm
    store: SignalStore


@dataclass
class CycleReport:
    status: str                          # "skipped" | "done" | "error"
    candidate: Optional[Candidate] = None
    features: dict = field(default_factory=dict)
    llm_invalid: list = field(default_factory=list)
    hold_reason: Optional[str] = None
    error: Optional[str] = None


def _ask(llm: Llm, role: str, prompt: tuple[str, str], version: str, cycle: int, cand: Candidate,
         ports: Ports, cfg: Settings, report: CycleReport) -> None:
    result = call_validated(llm, *prompt, AnalystView, prompt_version=version, max_retries=cfg.llm_max_retries)
    ports.store.record_llm_call(cycle, role, result)
    report.features[role], invalid = feature_from_result(result, cand.direction)
    if invalid:
        report.llm_invalid.append(role)


def _snapshot(symbol: str, close: datetime, m15: pd.DataFrame, trend: str, news: list) -> str:
    bars = m15.tail(SNAPSHOT_BARS).assign(timestamp=lambda d: d["timestamp"].astype(str))
    return json.dumps({
        "symbol": symbol, "candle_close_utc": close.isoformat(), "htf_trend": trend,
        "bars_m15": bars.to_dict(orient="records"),
        "news": [{"headline": n.headline, "source": n.source, "published_at": n.published_at.isoformat(),
                  "fetched_at": n.fetched_at.isoformat()} for n in news],
    }, default=float)


def run_once(symbol: str, candle_close: datetime, ports: Ports, cfg: Settings, code_version: str = "dev") -> CycleReport:
    if candle_close.tzinfo is None:
        raise ValueError("candle_close deve avere il fuso orario")
    cycle = ports.store.begin_cycle(symbol, candle_close)
    if cycle is None:
        return CycleReport("skipped")
    report, snapshot = CycleReport("done"), None
    try:
        bars = ports.market.closed_bars(symbol, cfg.timeframe, cfg.candles_count)
        htf = ports.market.closed_bars(symbol, cfg.htf_timeframe, HTF_BARS)
        m15, trend = add_indicators(closed_by(bars, M15, candle_close)), htf_trend(htf, candle_close)
        news = visible_news(ports.news.latest(symbol, NEWS_LIMIT), candle_close)
        snapshot = _snapshot(symbol, candle_close, m15, trend, news)

        generated = generate(symbol, bars, htf, candle_close)
        if generated is None:
            report.hold_reason = "NO_CANDIDATE"
        else:
            report.candidate, tech_features = generated
            report.features = {**tech_features, "tecnico": None, "macro": None}
            _ask(ports.technical, "tecnico", build_technical_prompt(symbol, m15, trend), TECHNICAL_PROMPT_VERSION,
                 cycle, report.candidate, ports, cfg, report)
            if news:  # senza notizie visibili il macro non ha nulla da dire: caratteristica assente
                _ask(ports.macro, "macro", build_macro_prompt(symbol, news), MACRO_PROMPT_VERSION,
                     cycle, report.candidate, ports, cfg, report)
    except Exception as exc:  # il ciclo si chiude come errore in archivio; il demone passa al simbolo successivo
        log.exception("ciclo %s %s fallito", symbol, candle_close)
        report.status, report.error = "error", f"{type(exc).__name__}: {exc}"
    ports.store.finish_cycle(cycle, report.status, report.error, snapshot, code_version, cfg.config_hash())
    return report
