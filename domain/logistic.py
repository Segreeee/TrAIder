"""Regressione logistica L2 con offset: p = sigmoid(logit(p0) + Σ β_k·x_k).

Niente intercetta: con β = 0 il modello restituisce esattamente p0, quindi le caratteristiche
possono solo aggiungere evidenza sopra la base geometrica. sklearn non supporta l'offset,
da qui l'ottimizzazione diretta con scipy. Le caratteristiche arrivano già standardizzate
(con statistiche calcolate solo sul passato) dal costruttore delle caratteristiche.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

MIN_TRADES_FOR_MODEL = 100


def predict(X: np.ndarray, offset: np.ndarray, beta: np.ndarray) -> np.ndarray:
    return expit(offset + X @ beta)


def fit_offset_logistic(X: np.ndarray, y: np.ndarray, offset: np.ndarray, l2: float = 1.0) -> np.ndarray:
    """Massima verosimiglianza penalizzata: Σ[log(1+e^z) − y·z] + l2/2·‖β‖², z = offset + Xβ."""
    def loss_and_grad(beta):
        z = offset + X @ beta
        loss = np.sum(np.logaddexp(0.0, z) - y * z) + 0.5 * l2 * beta @ beta
        grad = X.T @ (expit(z) - y) + l2 * beta
        return loss, grad

    res = minimize(loss_and_grad, np.zeros(X.shape[1]), jac=True, method="L-BFGS-B")
    if not res.success:
        raise RuntimeError(f"logistica non convergente: {res.message}")
    return res.x


@dataclass(frozen=True)
class Row:
    resolved_at: datetime
    x: np.ndarray
    y: float        # 1 = TP, 0 = SL
    offset: float   # logit(p0)


def walk_forward_fit(rows: Sequence[Row], t: datetime, l2: float = 1.0) -> Optional[np.ndarray]:
    """Fit con le sole righe risolte prima di t (niente sguardo al futuro). None se non ce ne sono."""
    past = [r for r in rows if r.resolved_at < t]
    if not past:
        return None
    X = np.array([r.x for r in past])
    return fit_offset_logistic(X, np.array([r.y for r in past]), np.array([r.offset for r in past]), l2)


def brier_skill_score(y: np.ndarray, p_model: np.ndarray, p_ref: np.ndarray) -> float:
    """1 − Brier(modello)/Brier(riferimento); riferimento = p0. > 0 significa meglio della base."""
    return 1.0 - np.mean((p_model - y) ** 2) / np.mean((p_ref - y) ** 2)


def bss_lower_bound(y: np.ndarray, p_model: np.ndarray, p_ref: np.ndarray,
                    level: float = 0.90, n_boot: int = 500, seed: int = 0) -> float:
    """Estremo inferiore dell'IC bootstrap bilaterale (`level`) del Brier skill score (Q-005, opzione a).
    Il modello si attiva solo se anche questa stima pessimistica è > 0: "BSS > 0" da solo
    si accendeva per caso su caratteristiche senza informazione."""
    rng = np.random.default_rng(seed)
    n = len(y)
    stats = []
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        ref = np.mean((p_ref[i] - y[i]) ** 2)
        if ref > 0:
            stats.append(1.0 - np.mean((p_model[i] - y[i]) ** 2) / ref)
    return float(np.quantile(stats, (1 - level) / 2)) if stats else float("-inf")


def choose_model(n_resolved: int, bss: Optional[float], min_n: int = MIN_TRADES_FOR_MODEL) -> str:
    """Logistica solo con abbastanza candidati risolti E abilità fuori campione positiva; altrimenti Beta."""
    if n_resolved >= min_n and bss is not None and bss > 0:
        return "logistica"
    return "beta"
