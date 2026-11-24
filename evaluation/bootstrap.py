"""Inferenza della preregistrazione (§5): bootstrap che ricampiona gruppi interi (i giorni UTC), non candidati.

Candidati consecutivi dello stesso simbolo condividono gran parte dell'orizzonte di 24 h: trattarli come
indipendenti stringerebbe gli intervalli. Il confronto tra varianti è appaiato perché la statistica riceve
gli stessi indici per tutte le varianti (es. ΔBSS = BSS(v7)[i] − BSS(v2)[i]).
"""
from collections import defaultdict
from collections.abc import Callable, Hashable, Sequence
from datetime import datetime, timezone

import numpy as np

B, SEED, LEVEL = 2000, 20261123, 0.95  # preregistrati


def cluster_ci(stat: Callable[[np.ndarray], float], clusters: Sequence[Hashable], n_boot: int = B,
               seed: int = SEED, level: float = LEVEL) -> tuple[float, float, float]:
    """(stima su tutti i dati, estremo inferiore, estremo superiore) dell'IC percentile.
    `stat` riceve un array di indici dei candidati; `clusters[k]` è il gruppo (giorno) del candidato k."""
    by_cluster = list(groups(clusters).values())
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n_boot):
        chosen = rng.integers(0, len(by_cluster), len(by_cluster))
        samples.append(stat(np.concatenate([by_cluster[c] for c in chosen])))
    alpha = (1 - level) / 2
    low, high = np.nanquantile(samples, [alpha, 1 - alpha])  # nan: statistica non definita in quel campione
    return float(stat(np.arange(len(clusters)))), float(low), float(high)


def groups(labels: Sequence[Hashable]) -> dict[Hashable, np.ndarray]:
    """Indici dei candidati per etichetta (giorno, simbolo, sessione), nell'ordine in cui compaiono."""
    out: dict[Hashable, list[int]] = defaultdict(list)
    for i, label in enumerate(labels):
        out[label].append(i)
    return {k: np.array(v) for k, v in out.items()}


def session_of(t: datetime) -> str:
    """Sessione per ora UTC della chiusura della candela, partizione delle 24 ore:
    Asia [22, 7), Londra [7, 13), New York [13, 22); la sovrapposizione Londra-New York va a New York."""
    if t.tzinfo is None:
        raise ValueError("serve un datetime con fuso orario")
    hour = t.astimezone(timezone.utc).hour
    if 7 <= hour < 13:
        return "Londra"
    if 13 <= hour < 22:
        return "New York"
    return "Asia"
