"""P5.09: metriche del giudice (D-012) su dati sintetici con valori noti, e la regola di promozione."""
import numpy as np
import pytest

from evaluation.judge_metrics import (ablation, flip_rate, hallucination_rate, judge_promotion_decision, kappa,
                                      reasons_auc, stability, veto_quality)

# 10 candidati: 4 perdite; il giudice veta 3 candidati, 2 dei quali sono perdite
LOSS = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=bool)
VETO = np.array([1, 1, 0, 0, 1, 0, 0, 0, 0, 0], dtype=bool)
DAYS = [f"d{i}" for i in range(10)]


def test_veto_quality_known_values():
    q = veto_quality(VETO, LOSS, DAYS)
    assert q["n_veto"] == 3 and q["n"] == 10
    assert q["precision"][0] == pytest.approx(2 / 3)
    assert q["lift"][0] == pytest.approx((2 / 3) / 0.4)
    assert q["recall"] == pytest.approx(2 / 4)


def test_ablation_known_values():
    traded = np.ones(10, dtype=bool)
    r_net = np.where(LOSS, -1.05, 1.45)
    y = (~LOSS).astype(float)
    p, p0 = np.full(10, 0.5), np.full(10, 0.4)
    a = ablation(VETO, traded, r_net, y, p, p0, DAYS)
    # senza veto: media di 4·(−1.05) + 6·1.45 = 0.45; con veto restano 2 perdite e 5 vincite: (−2.1 + 7.25)/7
    assert a["delta_ev"][0] == pytest.approx((-2.1 + 7.25) / 7 - 0.45)
    # ΔBSS: i vetati tornano a p0
    p_veto = np.where(VETO, p0, p)
    bss = lambda q: 1 - np.mean((q - y) ** 2) / np.mean((p0 - y) ** 2)  # noqa: E731
    assert a["delta_bss"][0] == pytest.approx(bss(p_veto) - bss(p))


def test_stability_flip_kappa():
    reps = np.array([[1, 1, 1], [0, 0, 0], [1, 0, 1], [0, 0, 0]], dtype=bool)
    assert stability(reps) == pytest.approx(3 / 4)
    assert flip_rate(np.array([1, 0, 1, 0], bool), np.array([1, 1, 1, 0], bool)) == pytest.approx(1 / 4)
    a = np.array([1, 1, 0, 0, 1, 0], bool)
    assert kappa(a, a) == pytest.approx(1.0)
    # accordo 4/6, atteso 0.5 → κ = (0.667 − 0.5) / 0.5 = 1/3
    assert kappa(a, np.array([1, 0, 0, 0, 1, 1], bool)) == pytest.approx(1 / 3)


def test_reasons_auc_and_hallucinations():
    failed = np.array([3, 2, 2, 1, 0, 0, 1, 0, 0, 0])
    assert reasons_auc(failed, LOSS) > 0.9  # più controlli falliti, più perdite
    judge = np.array([True, True, False, None, True], dtype=object)
    code = np.array([True, False, False, True, True])
    assert hallucination_rate(judge, code) == pytest.approx(1 / 4)  # None (controllo non dato) escluso


GOOD = {"n": 120, "n_veto": 35, "lift": (1.6, 1.2, 2.1), "delta_ev": (0.1, 0.02, 0.2), "stability": 0.97,
        "position_bias": 0.03, "kappa": 0.6}


def test_promotion_requires_30_vetoes_and_100_candidates():
    assert judge_promotion_decision(GOOD) == "promuovi a veto in linea"
    assert judge_promotion_decision({**GOOD, "n_veto": 29}) == "resta in ombra"
    assert judge_promotion_decision({**GOOD, "n": 99}) == "resta in ombra"
    assert judge_promotion_decision({**GOOD, "lift": (1.6, 0.9, 2.1)}) == "resta in ombra"
    assert judge_promotion_decision({**GOOD, "delta_ev": (0.1, -0.01, 0.2)}) == "resta in ombra"
    assert judge_promotion_decision({**GOOD, "stability": 0.94}) == "resta in ombra"
    assert judge_promotion_decision({**GOOD, "position_bias": 0.05}) == "resta in ombra"


def test_kappa_below_04_archives_line():
    assert judge_promotion_decision({**GOOD, "kappa": 0.39}) == "linea del giudice archiviata"
    assert judge_promotion_decision({**GOOD, "kappa": None}) == "promuovi a veto in linea"  # senza secondo giudice
