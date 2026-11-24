"""Metriche della preregistrazione (docs/PREREGISTRAZIONE.md, §4). Funzioni pure su sequenze di numeri:
y = 1 se l'esito è TP, 0 se SL (i TIMEOUT si escludono prima di chiamarle); p = probabilità stimata di TP."""
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike
from sklearn.metrics import roc_auc_score

from ports import Outcome

EPS = 1e-15  # log-loss finita anche con p = 0 o 1


def _arrays(y: ArrayLike, p: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    y_arr, p_arr = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    if y_arr.shape != p_arr.shape or y_arr.size == 0:
        raise ValueError(f"y e p devono avere la stessa lunghezza, non nulla ({y_arr.size} contro {p_arr.size})")
    return y_arr, p_arr


def brier(y: ArrayLike, p: ArrayLike) -> float:
    y_arr, p_arr = _arrays(y, p)
    return float(np.mean((p_arr - y_arr) ** 2))


def brier_skill(y: ArrayLike, p: ArrayLike, p_ref: ArrayLike) -> float:
    """1 − Brier(p) / Brier(p_ref): > 0 se p batte il riferimento (p0 nella preregistrazione)."""
    return 1.0 - brier(y, p) / brier(y, p_ref)


def log_loss(y: ArrayLike, p: ArrayLike) -> float:
    y_arr, p_arr = _arrays(y, p)
    p_arr = np.clip(p_arr, EPS, 1 - EPS)
    return float(-np.mean(y_arr * np.log(p_arr) + (1 - y_arr) * np.log(1 - p_arr)))


def auc(y: ArrayLike, p: ArrayLike) -> float | None:
    """Area sotto la curva ROC; None se c'è una sola classe (non definita)."""
    y_arr, p_arr = _arrays(y, p)
    if len(set(y_arr)) < 2:
        return None
    return float(roc_auc_score(y_arr, p_arr))


def calibration_deciles(y: ArrayLike, p: ArrayLike, bins: int = 10) -> list[dict]:
    """Affidabilità: candidati ordinati per p e divisi in `bins` gruppi di pari numerosità;
    per gruppo p media, frequenza osservata di TP e numerosità."""
    y_arr, p_arr = _arrays(y, p)
    order = np.argsort(p_arr, kind="stable")
    return [{"p_mean": float(p_arr[i].mean()), "y_rate": float(y_arr[i].mean()), "n": int(len(i))}
            for i in np.array_split(order, min(bins, len(order)))]


def max_drawdown(r: Sequence[float]) -> float:
    """Massima discesa (in R, ≥ 0) della somma cumulata dal picco precedente, partendo da 0."""
    if len(r) == 0:
        return 0.0
    equity = np.concatenate([[0.0], np.cumsum(np.asarray(r, dtype=float))])
    return float(np.max(np.maximum.accumulate(equity) - equity))


def summarize_r(outcomes: Sequence[Outcome]) -> dict:
    """R lordo e netto (TIMEOUT inclusi) e conteggio degli esiti."""
    net = [o.r_net for o in outcomes if o.r_net is not None]
    return {
        "n": len(outcomes),
        "tp": sum(o.result == "TP" for o in outcomes),
        "sl": sum(o.result == "SL" for o in outcomes),
        "timeout": sum(o.result == "TIMEOUT" for o in outcomes),
        "total_r_net": float(sum(net)),
        "total_r_gross": float(sum(o.r_gross for o in outcomes if o.r_gross is not None)),
        "mean_r_net": float(np.mean(net)) if net else 0.0,
    }


def ev_predicted_vs_realized(ev_predicted: ArrayLike, r_realized: ArrayLike) -> dict:
    """EV medio previsto alla decisione contro R netto medio realizzato sugli stessi candidati."""
    pred, real = _arrays(ev_predicted, r_realized)
    return {"predicted": float(pred.mean()), "realized": float(real.mean()), "gap": float(real.mean() - pred.mean())}
