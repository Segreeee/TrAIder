"""Revisore giudice (D-012), offline e in ombra: non decide, produce {veto, checks} su un candidato già deciso.

Alla cieca: i pareri degli analisti arrivano senza ruolo ("Parere 1", "Parere 2"), in ordine casuale con seme
registrato, senza forza né confidenza e senza dati del conto. I controlli calcolabili sono codice
(deterministic_checks), così si misura dove il giudice aggiunge qualcosa e dove allucina.
Il veto può solo togliere: TRADE → HOLD, mai il contrario (apply_veto).
"""
import random
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

CHECK_IDS = ("direzione_coerente", "motivazioni_supportate", "notizie_contrarie_assenti", "evento_imminente_assente")
JUDGE_PROMPT_VERSION = "giudice-v1"


class JudgeCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: Literal["direzione_coerente", "motivazioni_supportate", "notizie_contrarie_assenti", "evento_imminente_assente"]
    passed: bool
    evidence: Annotated[str, StringConstraints(max_length=300)]


class JudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    veto: bool
    checks: list[JudgeCheck] = Field(min_length=1, max_length=len(CHECK_IDS))


@dataclass(frozen=True)
class JudgeCase:
    """Ciò che il giudice vede di un candidato: niente ruoli, niente forza, niente conto."""
    symbol: str
    direction: Literal["BUY", "SELL"]
    d_sl_pips: float
    d_tp_pips: float
    htf_trend: str
    indicators: dict[str, float] = field(default_factory=dict)
    opinions: list[list[str]] = field(default_factory=list)   # motivazioni di ogni analista
    roles: list[str] = field(default_factory=list)             # ruolo di ogni parere: solo per la prova del bias
    news: list[str] = field(default_factory=list)              # titoli visibili alla chiusura


SYSTEM = (
    "Sei un revisore indipendente di segnali forex. Non scegli il trade: controlli se il candidato regge.\n"
    "Rispondi solo con JSON: {{\"veto\": true|false, \"checks\": [{{\"id\": ..., \"passed\": true|false, "
    "\"evidence\": \"...\"}}]}}.\n"
    "Controlli ammessi (id): {ids}.\n"
    "evidence cita solo dati presenti nel messaggio; se un dato manca, il controllo non passa. "
    "Metti veto solo se almeno un controllo non passa per un motivo concreto."
)


def build_judge_prompt(case: JudgeCase, seed: int, reverse: bool = False, labeled: bool = False) -> tuple[str, str]:
    """reverse: ordine dei pareri invertito (bias di posizione); labeled: ruoli nominati (bias di etichetta)."""
    roles = case.roles or [""] * len(case.opinions)
    pairs = list(zip(roles, case.opinions, strict=True))
    random.Random(seed).shuffle(pairs)  # ordine casuale ma riproducibile dal seme
    if reverse:
        pairs.reverse()
    pareri = "\n".join((f"Parere dell'analista {role}:" if labeled and role else f"Parere {i}:") + "\n"
                       + "\n".join(f"- {r}" for r in reasons)
                       for i, (role, reasons) in enumerate(pairs, start=1)) or "Nessun parere."
    indicators = ", ".join(f"{k} {v:.2f}" for k, v in case.indicators.items()) or "non disponibili"
    news = "\n".join(f"- {h}" for h in case.news) or "Nessuna notizia."
    user = (f"Candidato: {case.direction} {case.symbol}, stop a {case.d_sl_pips:.1f} pip, "
            f"target a {case.d_tp_pips:.1f} pip.\nTrend H1: {case.htf_trend}.\nIndicatori: {indicators}.\n\n"
            f"{pareri}\n\nNotizie:\n{news}")
    return SYSTEM.format(ids=", ".join(CHECK_IDS)), user


def deterministic_checks(case: JudgeCase) -> list[JudgeCheck]:
    """I controlli che il codice sa fare da solo: riferimento per misurare il giudice."""
    expected = "rialzista" if case.direction == "BUY" else "ribassista"
    return [JudgeCheck(id="direzione_coerente", passed=case.htf_trend == expected,
                       evidence=f"{case.direction} con trend H1 {case.htf_trend}")]


def apply_veto(final_action: str, veto: bool) -> str:
    """Azione finale con il veto in ombra: il veto toglie un TRADE, non ne crea mai uno."""
    return "HOLD" if veto else final_action
