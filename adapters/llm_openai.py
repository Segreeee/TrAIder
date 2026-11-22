"""LLM tramite API OpenAI-compatibile: Ollama in locale (http://localhost:11434/v1) o un fornitore
remoto scelto dall'utente (Q-001). Il client è iniettato; la validazione dell'output la fa
ports.call_validated, qui si fa solo il trasporto."""
import re
from typing import Sequence

from ports import LlmResponse

_THINK = re.compile(r"<think>.*?</think>", flags=re.DOTALL)


def build_client(*, base_url: str, api_key: str, timeout_s: float = 120.0):
    """base_url obbligatorio e senza default: nessuna chiamata parte verso un fornitore non scelto."""
    if not base_url:
        raise ValueError("base_url dell'LLM non configurato")
    from openai import OpenAI  # import qui: i test non costruiscono client reali
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)  # i retry li fa call_validated


class OpenAiLlm:
    def __init__(self, client, model: str, model_digest: str, seed: int = 7, secrets: Sequence[str] = ()):
        if not model_digest:
            raise ValueError("model_digest obbligatorio: senza non si sa quale modello ha prodotto un verdetto")
        self._client, self.model, self.model_digest, self._seed = client, model, model_digest, seed
        self._secrets = tuple(s for s in secrets if s)

    def _redact(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "***")
        return text

    def complete(self, system: str, user: str, *, temperature: float) -> LlmResponse:
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=temperature, seed=self._seed, response_format={"type": "json_object"},
            )
        except Exception as exc:
            # from None: la catena originale potrebbe contenere la chiave e finire in un log
            raise RuntimeError(self._redact(f"{type(exc).__name__}: {exc}")) from None
        # Modelli di ragionamento (deepseek-r1, qwen3) possono anteporre <think>...</think> al JSON.
        text = _THINK.sub("", resp.choices[0].message.content or "").strip()
        usage = resp.usage
        return LlmResponse(text, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)
