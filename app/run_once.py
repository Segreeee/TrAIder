"""Un ciclo per simbolo e candela chiusa: la Facade di D-001.

begin_cycle (idempotenza) → conto (perdita giornaliera prima di qualunque LLM) → dati → candidato baseline →
analisti LLM → ogni variante stima p e decide sullo stesso candidato → solo la variante di produzione
va al broker → finish_cycle con l'input completo.
"""
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

from app.candidates import M15, closed_by, generate, htf_trend
from app.config import Settings
from app.decide import Context, decide
from app.extractors import AnalystView, feature_from_result
from app.features import add_indicators
from app.prompts import MACRO_PROMPT_VERSION, TECHNICAL_PROMPT_VERSION, build_macro_prompt, build_technical_prompt
from app.variants import VARIANTS, available, estimate
from domain.costs import cost_pips
from domain.exposure import daily_loss_limit_reached
from domain.news import visible_news
from domain.pip import pip_size, pip_value_eur
from domain.probability import p0
from domain.types import Candidate, Direction
from ports import (AccountState, Broker, CandidateRecord, Fill, Llm, MarketData, NewsFeed, OrderRequest, SignalStore,
                   build_broker, call_validated)

log = logging.getLogger(__name__)
HTF_BARS, NEWS_LIMIT = 120, 10


@dataclass
class Ports:
    market: MarketData
    news: NewsFeed
    technical: Llm
    macro: Llm
    store: SignalStore
    broker: Broker


def broker_from_settings(cfg: Settings, make_live, make_sim) -> Broker:
    """Simulato per default; il broker reale solo con il doppio consenso (ports.build_broker)."""
    return build_broker(dry_run=cfg.dry_run, allow_live=cfg.allow_live_trading, make_live=make_live, make_sim=make_sim)


@dataclass
class CycleReport:
    status: str                          # "skipped" | "done" | "error"
    candidate: Optional[Candidate] = None
    features: dict = field(default_factory=dict)
    llm_invalid: list = field(default_factory=list)
    decision: Optional[str] = None       # della variante di produzione
    hold_reason: Optional[str] = None
    error: Optional[str] = None
    inputs: dict = field(default_factory=dict)   # tutto ciò che serve a app/replay.py, va in cycles.input_json


def _ask(llm: Llm, role: str, prompt: tuple[str, str], version: str, cycle: int, cand: Candidate,
         ports: Ports, cfg: Settings, report: CycleReport) -> None:
    log.info("analista %s (%s) in corso su %s", role, llm.model, cand.symbol)
    result = call_validated(llm, *prompt, AnalystView, prompt_version=version, max_retries=cfg.llm_max_retries)
    ports.store.record_llm_call(cycle, role, result)
    report.features[role], invalid = feature_from_result(result, cand.direction)
    if invalid:
        report.llm_invalid.append(role)


def _decide_all(symbol: str, cycle: int, cand: Candidate, last_bar: pd.Series, account: AccountState,
                called: set, ports: Ports, cfg: Settings, report: CycleReport) -> None:
    pip = pip_size(symbol)
    rate = ports.market.eur_quote_rate(symbol)
    pip_value = pip_value_eur(symbol, rate)
    # T-010: le distanze partono già dal prezzo di esecuzione (ask per i BUY; i SELL escono all'ask),
    # quindi lo spread non entra nel costo: c = commissione + slippage.
    # ponytail: commissione assente (ammessa solo in simulazione) vale 0 e sottostima il costo; va impostata nel .env
    cost = cost_pips(0.0, pip / 10, pip, cfg.commission_eur_per_lot or 0.0, pip_value, cfg.slippage_pips)
    ctx = Context(account.equity, account.open_positions, account.day_pnl, cost, pip_value, cfg)
    report.inputs.update(eur_quote_rate=rate, pip_value_eur=pip_value, cost_pips=cost, features=dict(report.features),
                         variants={})
    for variant in VARIANTS.values():
        if not available(variant, report.features, called):
            continue  # es. varianti macro senza notizie: non disponibili, non simulate
        est = estimate(variant, cand, report.features, ports.store.resolved(variant.name), cfg)
        invalid = any(role in report.llm_invalid for role in variant.features + variant.needs)
        d = decide(cand, est, ctx, llm_invalid=invalid)
        report.inputs["variants"][variant.name] = {"estimate": asdict(est), "llm_invalid": invalid}
        reason = d.hold_reason.value if d.hold_reason else None
        cid = ports.store.record_candidate(cycle, CandidateRecord(
            variant.name, cand, cost, est.p, d.p_star, d.ev, d.ev5, d.decision, reason,
            p0=p0(cand.d_sl, cand.d_tp), p5=est.p5, lot=d.lot, features=dict(report.features)))
        if variant.name == cfg.production_variant:
            report.decision, report.hold_reason = d.decision, reason
            if d.decision == "TRADE":
                fill = ports.broker.submit(OrderRequest(symbol, cand.direction, d.lot, cand.sl, cand.tp))
                ports.store.record_execution(cid, fill, d.lot, _slippage_pips(cand, fill, pip))


def _slippage_pips(cand: Candidate, fill: Fill, pip: float) -> Optional[float]:
    """Fill contro il prezzo del candidato, in pip; positivo = sfavorevole. None se l'ordine non è passato."""
    if not fill.accepted:
        return None
    sign = 1 if cand.direction is Direction.BUY else -1
    return sign * (fill.fill_price - cand.entry) / pip


def _bars(df: pd.DataFrame) -> list[dict]:
    return df.assign(timestamp=lambda d: d["timestamp"].astype(str)).to_dict(orient="records")


def run_once(symbol: str, candle_close: datetime, ports: Ports, cfg: Settings, code_version: str = "dev") -> CycleReport:
    if candle_close.tzinfo is None:
        raise ValueError("candle_close deve avere il fuso orario")
    cycle = ports.store.begin_cycle(symbol, candle_close)
    if cycle is None:
        log.info("%s: candela %s già elaborata, salto", symbol, candle_close)
        return CycleReport("skipped")
    report = CycleReport("done")
    report.inputs.update(symbol=symbol, candle_close_utc=candle_close.isoformat(), config=cfg.public_config())
    try:
        bars = ports.market.closed_bars(symbol, cfg.timeframe, cfg.candles_count)
        htf = ports.market.closed_bars(symbol, cfg.htf_timeframe, HTF_BARS)
        report.inputs.update(bars_m15=_bars(bars), bars_htf=_bars(htf))  # grezze: il replay rigenera il candidato
        last_close = bars["timestamp"].iloc[-1] + M15 if len(bars) else None
        if last_close != candle_close:  # MT5 non ha ancora la barra nuova: mai decidere su dati vecchi
            raise RuntimeError(f"candela {candle_close} non ancora disponibile (ultima barra chiusa: {last_close})")
        m15, trend = add_indicators(closed_by(bars, M15, candle_close)), htf_trend(htf, candle_close)
        news = visible_news(ports.news.latest(symbol, NEWS_LIMIT), candle_close)
        account = ports.broker.account()
        report.inputs.update(htf_trend=trend, account=asdict(account), news=[
            {"headline": n.headline, "source": n.source, "published_at": n.published_at.isoformat(),
             "fetched_at": n.fetched_at.isoformat()} for n in news])
        daily_stop = daily_loss_limit_reached(account.day_pnl, account.equity, cfg.daily_loss_limit_pct)

        generated = generate(symbol, bars, htf, candle_close)
        if generated is None:
            report.hold_reason = "NO_CANDIDATE"
        else:
            report.candidate, tech_features = generated
            report.features, called = {**tech_features, "tecnico": None, "macro": None}, set()
            if not daily_stop:  # oltre il limite giornaliero non si spende nulla in LLM
                _ask(ports.technical, "tecnico", build_technical_prompt(symbol, m15, trend), TECHNICAL_PROMPT_VERSION,
                     cycle, report.candidate, ports, cfg, report)
                called.add("tecnico")
                if news:  # senza notizie visibili il macro non ha nulla da dire: caratteristica assente
                    _ask(ports.macro, "macro", build_macro_prompt(symbol, news), MACRO_PROMPT_VERSION,
                         cycle, report.candidate, ports, cfg, report)
                    called.add("macro")
            _decide_all(symbol, cycle, report.candidate, m15.iloc[-1], account, called, ports, cfg, report)
    except Exception as exc:  # il ciclo si chiude come errore in archivio; il demone passa al simbolo successivo
        log.exception("ciclo %s %s fallito", symbol, candle_close)
        report.status, report.error = "error", f"{type(exc).__name__}: {exc}"
    snapshot = json.dumps(report.inputs, sort_keys=True, default=float)
    ports.store.finish_cycle(cycle, report.status, report.error, snapshot, code_version, cfg.config_hash())
    _log_summary(symbol, report)
    return report


def _log_summary(symbol: str, r: CycleReport) -> None:
    if r.status == "error":
        log.info("%s: ciclo in errore (%s)", symbol, r.error)
    elif r.candidate is None:
        log.info("%s: nessun candidato", symbol)
    else:
        log.info("%s: candidato %s -> %s%s", symbol, r.candidate.direction.value, r.decision,
                 f" ({r.hold_reason})" if r.hold_reason else "")
