"""Modello di probabilità della Fase 4 (specifica dell'utente). Tutte le distanze sono in pip,
misurate dal prezzo di esecuzione atteso (ask per BUY, bid per SELL); c = costo andata e ritorno.

    p0 = d_SL / (d_SL + d_TP)              probabilità di TP se il prezzo è un cammino casuale
    W  = (d_TP − c) / d_SL                 vincita netta in R
    L  = (d_SL + c) / d_SL                 perdita netta in R
    p* = L / (W + L) = (d_SL + c) / (d_SL + d_TP)   pareggio: EV(p*) = 0
    EV = p·W − (1 − p)·L                   con p = p0 vale −c/d_SL: senza vantaggio si perde il costo
"""
from dataclasses import dataclass


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
