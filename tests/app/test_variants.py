"""P3.26: stima di p e p5 per variante. Beta centrata su p0 finché il modello non è attivo
(≥ MIN_TRADES_FOR_MODEL candidati risolti e Brier skill > 0 fuori campione), poi logistica con offset."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.config import Settings
from app.variants import VARIANTS, available, estimate
from domain.probability import p0
from domain.types import Candidate, Direction
from ports import CandidateRecord, Outcome

T0 = datetime(2026, 3, 2, tzinfo=timezone.utc)
CAND = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, T0)  # d_SL 20, d_TP 30 pip -> p0 0.4
FEATS = {"momentum": 1.0, "rsi_dev": 0.2, "macd_hist_atr": 0.5, "tecnico": 2.0, "macro": None}


def _cfg(**kw):
    return Settings(_env_file=None, **kw)


def _history(n, rng, informative=True):
    out = []
    for i in range(n):
        m = float(rng.uniform(-3, 3))
        p_true = 1 / (1 + np.exp(-(np.log(0.4 / 0.6) + (1.2 * m if informative else 0))))
        win = rng.random() < p_true
        rec = CandidateRecord("v2-tecnica", CAND, 1.0, 0.4, 0.42, 0.0, 0.0, "HOLD", "GATE_EV",
                              p0=0.4, features={"momentum": m, "rsi_dev": 0.0, "macd_hist_atr": 0.0})
        out.append((rec, Outcome("TP" if win else "SL", None, None, None, "virtuale", T0 + timedelta(hours=i))))
    return out


def test_p0_variant_is_p0_without_data():
    est = estimate(VARIANTS["v1-p0"], CAND, FEATS, [], _cfg())
    assert est.p == pytest.approx(p0(20, 30)) and est.p5 < est.p and est.model == "beta"


def test_beta_moves_with_variant_history():
    hist = [(r, Outcome("TP", None, None, None, "virtuale", T0)) for r, _ in _history(30, np.random.default_rng(1))]
    est = estimate(VARIANTS["v2-tecnica"], CAND, FEATS, hist, _cfg())
    assert est.model == "beta" and est.p > 0.4


def test_timeouts_do_not_count_as_wins_or_losses():
    hist = [(r, Outcome("TIMEOUT", None, None, None, "virtuale", T0)) for r, _ in _history(30, np.random.default_rng(1))]
    assert estimate(VARIANTS["v2-tecnica"], CAND, FEATS, hist, _cfg()).p == pytest.approx(0.4)


def test_logistic_only_after_activation():
    rng = np.random.default_rng(5)
    few = estimate(VARIANTS["v2-tecnica"], CAND, FEATS, _history(80, rng), _cfg())
    many = estimate(VARIANTS["v2-tecnica"], CAND, FEATS, _history(600, rng), _cfg())
    assert few.model == "beta" and many.model == "logistica"
    assert many.p > 0.5 and many.p5 < many.p  # momentum +1 con β ≈ 1.2: p ≈ 0.69


@pytest.mark.xfail(strict=True, reason=(
    "Q-005: con la regola della specifica (BSS > 0 fuori campione) caratteristiche senza informazione "
    "attivano la logistica per caso in circa 4 semi su 10 (misurato: BSS 0.0002…0.0096). "
    "Serve una soglia più severa, da decidere con l'utente."))
def test_uninformative_features_keep_beta():
    est = estimate(VARIANTS["v2-tecnica"], CAND, FEATS, _history(600, np.random.default_rng(9), informative=False), _cfg())
    assert est.model == "beta"  # Brier skill fuori campione ≤ 0: il modello non si attiva


def test_availability_of_macro_variants():
    no_macro = {**FEATS, "macro": None}
    assert not available(VARIANTS["v4-llm-macro"], no_macro, called={"tecnico"})
    assert not available(VARIANTS["v5-consenso"], no_macro, called={"tecnico"})
    assert available(VARIANTS["v7-completo"], no_macro, called={"tecnico"})
    assert available(VARIANTS["v4-llm-macro"], {**FEATS, "macro": 1.0}, called={"tecnico", "macro"})


def test_consensus_without_agreement_has_no_edge():
    disagree = {**FEATS, "tecnico": 2.0, "macro": -1.0}
    hist = [(r, Outcome("TP", None, None, None, "virtuale", T0)) for r, _ in _history(30, np.random.default_rng(1))]
    est = estimate(VARIANTS["v5-consenso"], CAND, disagree, hist, _cfg())
    assert est.p == pytest.approx(0.4) and est.consensus is False
