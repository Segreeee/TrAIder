"""Decisione su un candidato, data la stima di p di una variante.

Ordine fisso: LLM non valido → perdita giornaliera → gate EV_5 → stesso simbolo → massimo posizioni →
esposizione per valuta → Kelly frazionario e lotto (rischio con costo incluso, domain.risk).
Distanze e costi in pip dal prezzo di esecuzione atteso (l'ingresso del candidato).
"""
from dataclasses import dataclass
from typing import Optional

from app.config import Settings
from app.variants import Estimate
from domain.costs import distance_pips
from domain.exposure import check_new_position, daily_loss_limit_reached
from domain.pip import pip_size
from domain.probability import Payoff, ev, ev_gate, kelly_risk_pct
from domain.risk import lot_size
from domain.types import Candidate, HoldReason


@dataclass(frozen=True)
class Context:
    equity: float
    positions: list[tuple[str, str]]   # posizioni aperte del bot: (simbolo, "BUY"/"SELL")
    day_pnl: float
    cost_pips: float
    pip_value_eur: float               # per lotto
    cfg: Settings


@dataclass(frozen=True)
class Decision:
    decision: str                      # "TRADE" | "HOLD"
    hold_reason: Optional[HoldReason]
    lot: float
    risk_pct: float
    p_star: float
    ev: float
    ev5: float


def decide(cand: Candidate, est: Estimate, ctx: Context, llm_invalid: bool = False) -> Decision:
    cfg, c = ctx.cfg, ctx.cost_pips
    pip = pip_size(cand.symbol)
    d_sl, d_tp = distance_pips(cand.entry, cand.sl, pip), distance_pips(cand.tp, cand.entry, pip)
    # Payoff costruito a mano: con costo ≥ d_TP la vincita è ≤ 0 e domain.payoff solleverebbe.
    pay = Payoff(win=(d_tp - c) / d_sl, loss=(d_sl + c) / d_sl, p_star=(d_sl + c) / (d_sl + d_tp))
    e, e5 = ev(est.p, pay), ev(est.p5, pay)

    def hold(reason: HoldReason) -> Decision:
        return Decision("HOLD", reason, 0.0, 0.0, pay.p_star, e, e5)

    if llm_invalid:
        return hold(HoldReason.LLM_INVALID)
    if daily_loss_limit_reached(ctx.day_pnl, ctx.equity, cfg.daily_loss_limit_pct):
        return hold(HoldReason.DAILY_LOSS)
    if pay.win <= 0 or not ev_gate(e5, cfg.ev_min)[0]:
        return hold(HoldReason.GATE_EV)
    if any(s.upper() == cand.symbol.upper() for s, _ in ctx.positions):
        return hold(HoldReason.SAME_SYMBOL)
    if len(ctx.positions) >= cfg.max_open_positions:
        return hold(HoldReason.MAX_POSITIONS)
    if not check_new_position(cand.symbol, cand.direction.value, ctx.positions,
                              cfg.max_open_positions, cfg.max_currency_exposure)[0]:
        return hold(HoldReason.EXPOSURE)

    risk = kelly_risk_pct(est.p, pay, cfg.kelly_lambda, cfg.risk_per_trade_pct)
    lot = lot_size(ctx.equity, risk, d_sl, c, ctx.pip_value_eur, cfg.min_lot, cfg.lot_step, cfg.max_lot) if risk > 0 else 0.0
    if lot == 0.0:
        return hold(HoldReason.LOT_BELOW_MIN)
    return Decision("TRADE", None, lot, risk, pay.p_star, e, e5)
