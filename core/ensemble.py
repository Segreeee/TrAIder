"""
Ensemble "LLM-as-a-judge": due analisti locali (Ollama) emettono ciascuno un
verdetto indipendente, un terzo modello locale (il giudice) arbitra e decide.
Nessun costo API.

Se un analista non risponde, il giudice decide con quello rimasto; se non
risponde nessuno, il chiamante ricade sul flusso single-model (vedi
`collect_persona_signals`: dict vuoto).
"""
import logging
from typing import Optional

from config.settings import settings
from core.prompt_builder import (
    MACRO_PERSONA_SYSTEM_PROMPT,
    MANAGER_SYSTEM_PROMPT,
    TECHNICAL_PERSONA_SYSTEM_PROMPT,
    build_manager_prompt,
)
from core.qwen_brain import QwenBrain, QwenBrainError, TradeSignal

logger = logging.getLogger(__name__)

TECHNICAL_LABEL = "Analista Tecnico"
MACRO_LABEL = "Analista Macro/Sentiment"


def _local(model: str) -> QwenBrain:
    """Client verso un modello Ollama. Nessun retry: se e' giu', fallisce subito."""
    return QwenBrain(
        api_key="ollama", base_url=settings.ollama_base_url, model=model,
        timeout=settings.ollama_timeout_seconds, max_retries=0,
    )


def build_judge() -> QwenBrain:
    """Il "cervello" principale: giudice dell'ensemble e fallback single-model (modello locale OLLAMA_MODEL_JUDGE)."""
    return _local(settings.ollama_model_judge)


def build_analysts() -> dict:
    """{etichetta: (brain, system_prompt)}: un modello Ollama per persona."""
    return {
        TECHNICAL_LABEL: (_local(settings.ollama_model_technical), TECHNICAL_PERSONA_SYSTEM_PROMPT),
        MACRO_LABEL: (_local(settings.ollama_model_macro), MACRO_PERSONA_SYSTEM_PROMPT),
    }


def active_analysts(analysts: dict, has_news: bool) -> dict:
    """
    Senza notizie reali l'analista macro/sentiment non ha nulla da analizzare:
    escluderlo evita che "inventi" un contesto macro dal solo grafico.
    """
    if has_news:
        return analysts
    return {k: v for k, v in analysts.items() if k != MACRO_LABEL}


def collect_persona_signals(base_prompt: str, analysts: dict) -> dict:
    """Interroga gli analisti in sequenza; quelli che falliscono vengono saltati (con warning)."""
    signals: dict = {}
    for label, (brain, system_prompt) in analysts.items():
        try:
            signals[label] = brain.get_trade_signal(base_prompt, system_prompt=system_prompt)
        except QwenBrainError as exc:
            logger.warning("%s non disponibile, escluso dall'ensemble: %s", label, exc)
    return signals


def judge_signal(
    judge: QwenBrain,
    persona_signals: dict,
    symbol: str,
    market_payload: dict,
    news_items: list,
    htf_trend: Optional[dict],
    expected_analysts: int = 2,
    account_balance: Optional[float] = None,
) -> TradeSignal:
    """Verdetto finale del giudice dati i verdetti degli analisti."""
    prompt = build_manager_prompt(
        symbol=symbol, timeframe=settings.timeframe, market_payload=market_payload,
        news_items=news_items,
        account_balance=account_balance if account_balance is not None else settings.account_balance,
        risk_per_trade_pct=settings.risk_per_trade_pct, htf_trend=htf_trend,
        persona_signals=persona_signals, expected_analysts=expected_analysts,
    )
    return judge.get_trade_signal(prompt, system_prompt=MANAGER_SYSTEM_PROMPT)
