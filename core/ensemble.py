"""
Ensemble "LLM-as-a-judge": due analisti locali (Ollama) emettono ciascuno un
verdetto indipendente, Qwen (API) arbitra e decide. Costo a pagamento: una
sola chiamata (il giudice).

Se un analista non risponde, il giudice decide con quello rimasto; se non
risponde nessuno, il chiamante ricade sul flusso Qwen-only (vedi
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


def build_analysts() -> dict:
    """{etichetta: (brain, system_prompt)}: un modello Ollama per persona. Nessun retry: se e' giu', fallisce subito."""

    def local(model: str) -> QwenBrain:
        return QwenBrain(
            api_key="ollama", base_url=settings.ollama_base_url, model=model,
            timeout=settings.ollama_timeout_seconds, max_retries=0,
        )

    return {
        TECHNICAL_LABEL: (local(settings.ollama_model_technical), TECHNICAL_PERSONA_SYSTEM_PROMPT),
        MACRO_LABEL: (local(settings.ollama_model_macro), MACRO_PERSONA_SYSTEM_PROMPT),
    }


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
) -> TradeSignal:
    """Verdetto finale del giudice (Qwen) dati i verdetti degli analisti."""
    prompt = build_manager_prompt(
        symbol=symbol, timeframe=settings.timeframe, market_payload=market_payload,
        news_items=news_items, account_balance=settings.account_balance,
        risk_per_trade_pct=settings.risk_per_trade_pct, htf_trend=htf_trend,
        persona_signals=persona_signals,
    )
    return judge.get_trade_signal(prompt, system_prompt=MANAGER_SYSTEM_PROMPT)
