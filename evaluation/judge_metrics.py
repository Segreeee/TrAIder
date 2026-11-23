"""Metriche del revisore giudice (D-012, preregistrazione §4) e regola di promozione.

Funzioni su array allineati per candidato: veto (bool), perdita (r_net < 0 o SL), giorno per il bootstrap.
Un veto è "buono" se il candidato era una perdita: precisione = P(perdita | veto), lift = precisione / P(perdita).
"""
from collections.abc import Sequence
from typing import Any

import numpy as np
from sklearn.metrics import cohen_kappa_score

from evaluation.bootstrap import cluster_ci
from evaluation.metrics import auc, brier_skill

MIN_CANDIDATES, MIN_VETOES, MIN_STABILITY, MAX_POSITION_BIAS, MIN_KAPPA = 100, 30, 0.95, 0.05, 0.4


def _ratio(num: np.ndarray, den: np.ndarray) -> float:
    return float(num.sum() / den.sum()) if den.sum() else float("nan")


def veto_quality(veto: np.ndarray, loss: np.ndarray, days: Sequence) -> dict:
    """Precisione e lift con IC per giorno; richiamo = P(veto | perdita)."""
    veto, loss = np.asarray(veto, bool), np.asarray(loss, bool)
    precision = cluster_ci(lambda i: _ratio(veto[i] & loss[i], veto[i]), days)
    lift = cluster_ci(lambda i: _ratio(veto[i] & loss[i], veto[i]) / loss[i].mean() if loss[i].any()
                      else float("nan"), days)
    return {"n": len(veto), "n_veto": int(veto.sum()), "precision": precision, "lift": lift,
            "recall": _ratio(veto & loss, loss)}


def ablation(veto: np.ndarray, traded: np.ndarray, r_net: np.ndarray, y: np.ndarray, p: np.ndarray,
             p0: np.ndarray, days: Sequence) -> dict:
    """ΔEV: R netto medio dei TRADE che restano dopo il veto meno quello di tutti i TRADE.
    ΔBSS: un candidato vetato torna a p0 (il giudice toglie il vantaggio dichiarato), BSS contro p0."""
    veto, traded = np.asarray(veto, bool), np.asarray(traded, bool)
    r_net, y, p, p0 = (np.asarray(a, float) for a in (r_net, y, p, p0))
    p_veto = np.where(veto, p0, p)

    def delta_ev(i: np.ndarray) -> float:
        kept, all_ = r_net[i][traded[i] & ~veto[i]], r_net[i][traded[i]]
        return float(kept.mean() - all_.mean()) if len(kept) and len(all_) else float("nan")

    return {"delta_ev": cluster_ci(delta_ev, days),
            "delta_bss": cluster_ci(lambda i: brier_skill(y[i], p_veto[i], p0[i]) - brier_skill(y[i], p[i], p0[i]),
                                    days)}


def stability(repetitions: np.ndarray) -> float:
    """Quota di candidati con lo stesso veto in tutte le ripetizioni (righe = candidati)."""
    reps = np.asarray(repetitions, bool)
    return float(np.mean(reps.all(axis=1) | ~reps.any(axis=1)))


def flip_rate(a: np.ndarray, b: np.ndarray) -> float:
    """Quota di veti che cambiano tra due condizioni: ordine invertito (bias di posizione) o ruoli nominati
    (bias di etichetta)."""
    return float(np.mean(np.asarray(a, bool) != np.asarray(b, bool)))


def kappa(a: np.ndarray, b: np.ndarray) -> float:
    """Accordo tra due giudici oltre il caso (Cohen)."""
    return float(cohen_kappa_score(np.asarray(a, bool), np.asarray(b, bool)))


def reasons_auc(failed_checks: np.ndarray, loss: np.ndarray) -> float | None:
    """AUC delle motivazioni: il numero di controlli falliti distingue le perdite?"""
    return auc(np.asarray(loss, float), np.asarray(failed_checks, float))


def hallucination_rate(judge_checks: np.ndarray, code_checks: np.ndarray) -> float:
    """Quota di controlli calcolabili dal codice in cui il giudice dice il contrario; None = non dato, escluso."""
    pairs = [(j, c) for j, c in zip(judge_checks, code_checks, strict=True) if j is not None]
    return float(np.mean([j != c for j, c in pairs])) if pairs else float("nan")


def judge_promotion_decision(m: dict[str, Any]) -> str:
    """Soglie di D-012. Con kappa < 0.4 tra due giudici la linea si archivia, qualunque cosa dicano le altre."""
    if m.get("kappa") is not None and m["kappa"] < MIN_KAPPA:
        return "linea del giudice archiviata"
    if (m["n"] >= MIN_CANDIDATES and m["n_veto"] >= MIN_VETOES and m["lift"][1] > 1 and m["delta_ev"][1] > 0
            and m["stability"] >= MIN_STABILITY and m["position_bias"] < MAX_POSITION_BIAS):
        return "promuovi a veto in linea"
    return "resta in ombra"
