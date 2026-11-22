"""Porte verso il mondo esterno (D-001). Il dominio non le conosce; l'orchestrazione le riceve
già costruite. Ogni porta ha un fake in tests/fakes.py e un contratto in tests/contracts/.
Le porte Broker e SignalStore arrivano nei passi P3.13–P3.14."""
import time
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel, ValidationError

from domain.news import NewsItem

__all__ = ["Llm", "LlmResponse", "LlmResult", "MarketData", "NewsFeed", "NewsItem", "call_validated"]


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