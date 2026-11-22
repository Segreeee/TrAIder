"""Varianti di combinazione (D-003, Fase 5) come Strategy: stesse candele, stesso candidato, stima di p diversa.

Ogni variante stima p e p5 dal proprio storico risolto (Q-004: anche i candidati non eseguiti):
- Beta(κ·p0 + TP, κ·(1−p0) + SL) finché il modello non è attivo; i TIMEOUT non contano;
- logistica con offset logit(p0) quando ci sono ≥ MIN_TRADES_FOR_MODEL esiti e Brier skill > 0
  fuori campione (ultimo 30% in ordine di tempo); p5 da bootstrap.
Caratteristiche mancanti (LLM non chiamato o non valido) valgono 0, il centro della loro scala.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.special import expit, logit

from app.config import Settings
from domain.logistic import brier_skill_score, choose_model, fit_offset_logistic, predict
from domain.probability import beta_posterior, p0
from domain.types import Candidate
from ports import CandidateRecord, Outcome

TECH = ("momentum", "rsi_dev", "macd_hist_atr")
BOOTSTRAP, SEED, TEST_SHARE = 100, 0, 0.3


@dataclass(frozen=True)
class Variant:
    name: str
    features: tuple[str, ...]          # caratteristiche del modello
    needs: tuple[str, ...] = ()        # ruoli LLM che devono essere stati chiamati, altrimenti non disponibile
    consensus: bool = False            # solo se tecnico e macro concordano con il candidato


VARIANTS = {v.name: v for v in (
    Variant("v1-p0", ()),
    Variant("v2-tecnica", TECH),
    Variant("v3-llm-tecnico", TECH + ("tecnico",), ("tecnico",)),
    Variant("v4-llm-macro", TECH + ("macro",), ("macro",)),
    Variant("v5-consenso", TECH, ("tecnico", "macro"), consensus=True),
    Variant("v7-completo", TECH + ("tecnico", "macro")),
)}


@dataclass(frozen=True)
class Estimate:
    p: float
    p5: float
    model: str                        # "beta" | "logistica"
    consensus: Optional[bool] = None


def available(variant: Variant, features: dict, called: set) -> bool:
    return all(role in called for role in variant.needs)


def _agree(features: dict) -> bool:
    return (features.get("tecnico") or 0) > 0 and (features.get("macro") or 0) > 0


def _x(features: dict, keys: tuple[str, ...]) -> list[float]:
    return [features.get(k) if features.get(k) is not None else 0.0 for k in keys]


def _logistic(variant: Variant, x_now: list[float], off_now: float, decided: list, cfg: Settings) -> Optional[Estimate]:
    X = np.array([_x(r.features, variant.features) for r, _ in decided])
    off = np.array([logit(r.p0 if r.p0 is not None else p0(r.candidate.d_sl, r.candidate.d_tp)) for r, _ in decided])
    y = np.array([1.0 if o.result == "TP" else 0.0 for _, o in decided])
    split = int(len(y) * (1 - TEST_SHARE))
    beta_train = fit_offset_logistic(X[:split], y[:split], off[:split])
    bss = brier_skill_score(y[split:], predict(X[split:], off[split:], beta_train), expit(off[split:]))
    if choose_model(len(y), bss, cfg.min_trades_for_model) != "logistica":
        return None
    x, o = np.array([x_now]), np.array([off_now])
    p = float(predict(x, o, fit_offset_logistic(X, y, off))[0])
    rng = np.random.default_rng(SEED)
    boot = [predict(x, o, fit_offset_logistic(X[i], y[i], off[i]))[0]
            for i in (rng.integers(0, len(y), len(y)) for _ in range(BOOTSTRAP))]
    return Estimate(p, float(np.quantile(boot, 0.05)), "logistica")


def estimate(variant: Variant, cand: Candidate, features: dict,
             history: list[tuple[CandidateRecord, Outcome]], cfg: Settings) -> Estimate:
    base = p0(cand.d_sl, cand.d_tp)
    prior = beta_posterior(base, cfg.beta_kappa, 0, 0)
    consensus = _agree(features) if variant.consensus else None
    if not variant.features or consensus is False:  # nessun vantaggio dichiarabile
        return Estimate(base, prior.quantile(0.05), "beta", consensus)

    decided = [(r, o) for r, o in history if o.result in ("TP", "SL")]
    if variant.consensus:
        decided = [(r, o) for r, o in decided if _agree(r.features)]
    if len(decided) >= cfg.min_trades_for_model:
        est = _logistic(variant, _x(features, variant.features), float(logit(base)), decided, cfg)
        if est is not None:
            return Estimate(est.p, est.p5, est.model, consensus)
    wins = sum(o.result == "TP" for _, o in decided)
    post = beta_posterior(base, cfg.beta_kappa, wins, len(decided) - wins)
    return Estimate(post.mean, post.quantile(0.05), "beta", consensus)
