"""
LLM Execution (Qwen).

Chiama il modello Qwen tramite un endpoint OpenAI-compatible (package `openai`)
forzando l'output in JSON puro, valida lo schema atteso e gestisce le
eccezioni piu' comuni (timeout, rate limit, JSON malformato, campi mancanti).
"""
import json
import logging
import re
from typing import Optional, TypedDict

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from config.settings import settings
from core.prompt_builder import REASONING_SYSTEM_PROMPT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"BUY", "SELL", "HOLD"}

REQUIRED_FIELDS = {
    "action": str,
    "confidence_percentage": (int, float),
    "lot_size": (int, float),
    "take_profit_price": (int, float),
    "stop_loss_price": (int, float),
    "reasoning": str,
}


class TradeSignal(TypedDict):
    action: str
    confidence_percentage: int
    lot_size: float
    take_profit_price: float
    stop_loss_price: float
    reasoning: str


class QwenBrainError(Exception):
    """Errore generico nella comunicazione o nel parsing della risposta di Qwen."""


class QwenBrain:
    """
    Wrapper attorno a un client OpenAI-compatible. Senza argomenti punta al
    provider Qwen (da settings); passando base_url/model/api_key puo' puntare a
    qualunque altro endpoint compatibile (es. Ollama locale per gli analisti).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ):
        api_key = api_key if api_key is not None else settings.qwen_api_key
        if not api_key:
            logger.warning(
                "QWEN_API_KEY non impostata: le chiamate al modello falliranno finche' "
                "non viene configurata la variabile d'ambiente."
            )
        self._model = model or settings.qwen_model
        self._client = OpenAI(
            api_key=api_key or "missing-key",
            base_url=base_url or settings.qwen_base_url,
            timeout=timeout if timeout is not None else settings.llm_timeout_seconds,
            max_retries=max_retries if max_retries is not None else settings.llm_max_retries,
        )

    def _chat_completion(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool) -> str:
        """Esegue la chiamata API grezza e ne isola la gestione delle eccezioni; ritorna il contenuto testuale."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"} if json_mode else None,
                temperature=temperature,
            )
            content = response.choices[0].message.content

        except APITimeoutError as exc:
            raise QwenBrainError(f"Timeout nella chiamata a Qwen: {exc}") from exc
        except APIConnectionError as exc:
            raise QwenBrainError(f"Errore di connessione verso il provider Qwen: {exc}") from exc
        except APIStatusError as exc:
            raise QwenBrainError(
                f"Il provider Qwen ha restituito un errore HTTP {exc.status_code}: {exc.message}"
            ) from exc
        except Exception as exc:  # safety net su errori imprevisti del SDK
            raise QwenBrainError(f"Errore imprevisto durante la chiamata a Qwen: {exc}") from exc

        if not content:
            raise QwenBrainError("Risposta vuota da Qwen.")
        return content

    def run_reasoning_pass(self, user_prompt: str) -> str:
        """
        Fase 1 (opzionale) del ciclo decisionale "a due passi": chiede al modello
        un'analisi libera, non vincolata al formato JSON, prima del verdetto finale.
        Da' effettivamente al modello "piu' tempo per analizzare" in termini di
        token di ragionamento prodotti prima di dover committarsi a una decisione.
        """
        return self._chat_completion(
            system_prompt=SYSTEM_PROMPT + "\n\n" + REASONING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            json_mode=False,
        )

    def get_trade_signal(self, user_prompt: str, system_prompt: Optional[str] = None) -> TradeSignal:
        """
        Invia il prompt a Qwen (fase decisionale, JSON puro) e restituisce un
        TradeSignal validato. Solleva QwenBrainError in caso di timeout, errore
        HTTP o JSON non conforme.

        `system_prompt` permette di sostituire l'identita' di base (usato per
        le personas dell'ensemble e per il manager arbitro); default SYSTEM_PROMPT.
        """
        raw_content = self._chat_completion(
            system_prompt=system_prompt or SYSTEM_PROMPT, user_prompt=user_prompt, temperature=0.2, json_mode=True,
        )
        return self._parse_and_validate(raw_content)

    @staticmethod
    def _parse_and_validate(raw_content: Optional[str]) -> TradeSignal:
        if not raw_content:
            raise QwenBrainError("Risposta vuota da Qwen.")

        # Modelli "reasoning" locali (deepseek-r1) possono anteporre <think>...</think> al JSON.
        raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise QwenBrainError(f"JSON malformato restituito da Qwen: {exc}. Contenuto: {raw_content!r}") from exc

        if not isinstance(data, dict):
            raise QwenBrainError(f"Atteso un oggetto JSON, ricevuto: {type(data).__name__}")

        missing = [field for field in REQUIRED_FIELDS if field not in data]
        if missing:
            raise QwenBrainError(f"Campi mancanti nella risposta di Qwen: {missing}. Payload: {data}")

        for field, expected_type in REQUIRED_FIELDS.items():
            if not isinstance(data[field], expected_type):
                raise QwenBrainError(
                    f"Campo '{field}' di tipo errato: atteso {expected_type}, "
                    f"ricevuto {type(data[field]).__name__}. Payload: {data}"
                )

        if data["action"] not in VALID_ACTIONS:
            raise QwenBrainError(f"Valore 'action' non valido: {data['action']!r}. Attesi: {VALID_ACTIONS}")

        signal: TradeSignal = {
            "action": data["action"],
            "confidence_percentage": int(data["confidence_percentage"]),
            "lot_size": float(data["lot_size"]),
            "take_profit_price": float(data["take_profit_price"]),
            "stop_loss_price": float(data["stop_loss_price"]),
            "reasoning": str(data["reasoning"]),
        }
        return signal
