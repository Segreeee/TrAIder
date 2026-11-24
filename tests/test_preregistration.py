"""P5.01: la preregistrazione esiste e fissa, prima dei dati, metriche, soglie, varianti e regole di decisione."""
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "PREREGISTRAZIONE.md"

REQUIRED = [
    # metrica primaria e confronto
    "Brier skill score", "R netto", "v7-completo", "v2-tecnica",
    # le varianti (v6 resta fuori finché P5.04 non la attiva)
    "v1-p0", "v3-llm-tecnico", "v4-llm-macro", "v5-consenso",
    # inferenza
    "B = 2000", "seme 20261123", "IC 95%", "per giorno",
    # soglie
    "100 candidati", "300", "30 giorni",
    # metriche secondarie e del giudice (D-012)
    "log-loss", "calibrazione", "AUC", "drawdown", "precisione dei veti", "kappa",
    # regole
    "nessuna modifica in corsa", "non concludente", "config_hash",
]


def test_preregistration_exists_and_lists_metrics():
    text = DOC.read_text(encoding="utf-8")
    missing = [key for key in REQUIRED if key not in text]
    assert not missing, f"mancano in PREREGISTRAZIONE.md: {missing}"
