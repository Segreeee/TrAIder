"""Porte verso il mondo esterno (D-001). Il dominio non le conosce; l'orchestrazione le riceve
già costruite. Ogni porta ha un fake in tests/fakes.py e un contratto in tests/contracts/."""
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel, ValidationError

from domain.news import NewsItem
from domain.types import Candidate, Direction

__all__ = ["AccountState", "Broker", "Fill", "OrderRequest", "Position", "build_broker", "CandidateRecord", "Outcome", "SignalStore", "Llm", "LlmResponse", "LlmResult", "MarketData", "NewsFeed", "NewsItem", "call_validated"]


@runtime_checkable
class MarketData(Protocol):
    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Ultime `count` candele chiuse. Colonne: timestamp (apertura, UTC tz-aware),
        open, high, low, close, volume, spread (in punti)."""
        ...


@runtime_checkable
class NewsFeed(Protocol):
    def latest(self, symbol: str, limit: int) -> list[NewsItem]:
        """Notizie più recenti per il simbolo, con published_at e fetched_at tz-aware."""
        ...


# --- LLM --------------------------------------------------------------------- #
@dataclass(frozen=True)
class LlmResponse:
    text: str
    tokens_in: int
    tokens_out: int


@runtime_checkable
class Llm(Protocol):
    model: str
    model_digest: str  # identifica i pesi esatti: lo stesso nome può cambiare modello nel tempo

    def complete(self, system: str, user: str, *, temperature: float) -> LlmResponse: ...


@dataclass(frozen=True)
class LlmResult:
    parsed: Optional[BaseModel]
    raw: str
    model: str
    model_digest: str
    prompt_version: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    attempts: int
    schema_valid: bool
    error: str = ""


def call_validated(
    llm: Llm, system: str, user: str, schema: type[BaseModel], *, prompt_version: str, max_retries: int = 2,
) -> LlmResult:
    """Unico punto di chiamata degli LLM: temperatura 0, output validato da `schema`,
    al massimo max_retries + 1 tentativi. Non solleva: un fallimento torna con schema_valid=False
    e l'errore, così il ciclo lo archivia (HoldReason.LLM_INVALID) invece di interrompersi."""
    raw, error, tokens_in, tokens_out = "", "", 0, 0
    start = time.perf_counter()
    for attempt in range(1, max_retries + 2):
        try:
            resp = llm.complete(system, user, temperature=0.0)
        except Exception as exc:  # trasporto (rete, Ollama giù): conta come tentativo fallito
            error = f"{type(exc).__name__}: {exc}"
            continue
        raw, tokens_in, tokens_out = resp.text, tokens_in + resp.tokens_in, tokens_out + resp.tokens_out
        try:
            parsed = schema.model_validate_json(raw)
        except ValidationError as exc:
            error = f"schema: {exc.errors()[0]['msg']}"
            continue
        return LlmResult(parsed, raw, llm.model, llm.model_digest, prompt_version,
                         (time.perf_counter() - start) * 1000, tokens_in, tokens_out, attempt, True)
    return LlmResult(None, raw, llm.model, llm.model_digest, prompt_version,
                     (time.perf_counter() - start) * 1000, tokens_in, tokens_out, max_retries + 1, False, error)


# --- Broker ------------------------------------------------------------------ #
@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    direction: Direction
    lots: float
    sl: float
    tp: float


@dataclass(frozen=True)
class Fill:
    mode: str              # "sim" | "mt5"
    accepted: bool
    fill_price: float
    spread: float          # in prezzo (ask − bid) al momento del submit
    ticket: Optional[int]
    reason: str = ""


@dataclass(frozen=True)
class Position:
    symbol: str
    direction: Direction
    lots: float
    entry: float
    sl: float
    tp: float
    ticket: Optional[int] = None


@dataclass(frozen=True)
class AccountState:
    equity: float
    open_positions: list[tuple[str, str]]  # [(simbolo, "BUY"/"SELL")], solo posizioni del bot
    day_pnl: float                         # realizzato oggi (con commissioni e swap) + aperto


@runtime_checkable
class Broker(Protocol):
    def submit(self, order: OrderRequest) -> Fill: ...
    def positions(self) -> list[Position]: ...


def build_broker(
    *, dry_run: bool, allow_live: bool, make_live: Callable[[], Broker], make_sim: Callable[[], Broker],
) -> Broker:
    """Doppio consenso: il broker reale si costruisce solo con dry_run False E allow_live True.
    I flag devono essere bool veri: una stringa come "false" è vera in Python e aprirebbe il conto."""
    if type(dry_run) is not bool or type(allow_live) is not bool:
        raise TypeError("dry_run e allow_live devono essere bool")
    if not dry_run and allow_live:
        return make_live()
    return make_sim()

# --- Archivio ---------------------------------------------------------------- #
@dataclass(frozen=True)
class CandidateRecord:
    """Un candidato con tutto ciò che è servito a decidere (regola: ogni segnale va in archivio)."""
    variant: str
    candidate: Candidate
    cost_pips: float
    p: float
    p_star: float
    ev: float
    ev5: float
    decision: str                       # "TRADE" | "HOLD"
    hold_reason: Optional[str] = None   # HoldReason.value se HOLD


@dataclass(frozen=True)
class Outcome:
    result: str                 # "TP" | "SL" | "TIMEOUT"
    exit_price: Optional[float]
    r_net: Optional[float]
    r_gross: Optional[float]
    resolved_by: str            # "virtuale" | "broker"
    resolved_at: datetime


@runtime_checkable
class SignalStore(Protocol):
    def begin_cycle(self, symbol: str, candle_close_utc: datetime) -> Optional[int]:
        """Id del ciclo, o None se quella candela per quel simbolo è già stata elaborata."""
        ...

    def last_cycle(self, symbol: str) -> Optional[datetime]: ...
    def record_llm_call(self, cycle_id: int, role: str, result: LlmResult) -> None: ...

    def record_candidate(self, cycle_id: int, record: CandidateRecord) -> int:
        """Id del candidato; ValueError se la variante è già registrata per il ciclo."""
        ...

    def record_execution(self, candidate_id: int, fill: Fill, lots: float) -> None: ...

    def record_outcome(self, candidate_id: int, outcome: Outcome) -> bool:
        """True se scritto, False se il candidato aveva già un esito."""
        ...

    def pending_candidates(self) -> list[tuple[int, CandidateRecord]]: ...