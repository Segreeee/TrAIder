"""Modello di probabilità della Fase 4 (specifica dell'utente). Tutte le distanze sono in pip,
misurate dal prezzo di esecuzione atteso (ask per BUY, bid per SELL); c = costo andata e ritorno.

    p0 = d_SL / (d_SL + d_TP)              probabilità di TP se il prezzo è un cammino casuale
    W  = (d_TP − c) / d_SL                 vincita netta in R
    L  = (d_SL + c) / d_SL                 perdita netta in R
    p* = L / (W + L) = (d_SL + c) / (d_SL + d_TP)   pareggio: EV(p*) = 0
    EV = p·W − (1 − p)·L                   con p = p0 vale −c/d_SL: senza vantaggio si perde il costo
"""
from dataclasses import dataclass
from typing import Optional

from scipy.stats import beta as beta_dist

from domain.types import HoldReason


def p0(d_sl: float, d_tp: float) -> float:
    if d_sl <= 0 or d_tp <= 0:
        raise ValueError("d_sl e d_tp devono essere positivi")
    return d_sl / (d_sl + d_tp)


@dataclass(frozen=True)
class Payoff:
    win: float     # W
    loss: float    # L
    p_star: float  # p*


def payoff(d_sl: float, d_tp: float, cost: float) -> Payoff:
    if d_sl <= 0 or d_tp <= 0:
        raise ValueError("d_sl e d_tp devono essere positivi")
    if not 0 <= cost < d_tp:
        raise ValueError("il costo deve essere in [0, d_tp)")
    win = (d_tp - cost) / d_sl
    loss = (d_sl + cost) / d_sl
    return Payoff(win=win, loss=loss, p_star=loss / (win + loss))


def ev(p: float, pay: Payoff) -> float:
    """Valore atteso in R per operazione."""
    return p * pay.win - (1 - p) * pay.loss


@dataclass(frozen=True)
class BetaPosterior:
    """Beta(κ·p0 + vinti, κ·(1−p0) + persi): a priori centrata su p0 con peso di κ osservazioni."""
    a: float
    b: float

    @property
    def mean(self) -> float:
        return self.a / (self.a + self.b)

    def quantile(self, q: float) -> float:
        return float(beta_dist.ppf(q, self.a, self.b))

    def prob_above(self, x: float) -> float:
        """P(p > x | dati): con x = p* è la confidenza mostrata all'utente."""
        return float(beta_dist.sf(x, self.a, self.b))


def beta_posterior(p0: float, kappa: float, wins: float, losses: float) -> BetaPosterior:
    if not 0 < p0 < 1:
        raise ValueError("p0 deve essere in (0, 1)")
    if kappa <= 0 or wins < 0 or losses < 0:
        raise ValueError("kappa positivo, vinti e persi non negativi")
    return BetaPosterior(a=kappa * p0 + wins, b=kappa * (1 - p0) + losses)


def ev5(post: BetaPosterior, pay: Payoff) -> float:
    """EV valutato al quantile 5% di p: il numero prudente su cui decide il gate."""
    return ev(post.quantile(0.05), pay)


def kelly_risk_pct(p: float, pay: Payoff, lam: float = 0.25, cap: float = 1.0) -> float:
    """Rischio % = min(cap, λ·f*), f* = p − (1−p)/(W/L). La perdita L include il costo,
    coerente con il rischio per operazione di domain.risk. f* ≤ 0 (cioè p ≤ p*) -> 0."""
    f_star = p - (1 - p) * pay.loss / pay.win
    if f_star <= 1e-12:  # a p = p* f* è 0 in teoria, ~1e-17 in virgola mobile
        return 0.0
    return min(cap, lam * f_star * 100)


def ev_gate(ev5_value: float, ev_min: float = 0.0) -> tuple[bool, Optional[HoldReason]]:
    if ev5_value > ev_min:
        return True, None
    return False, HoldReason.GATE_EV
