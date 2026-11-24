"""Contratto della porta Llm: lo stesso controllo gira sul fake e (P3.17) sull'adattatore Ollama."""
from ports import LlmResponse


def check_llm(adapter):
    assert isinstance(adapter.model, str) and adapter.model, "nome del modello mancante"
    assert isinstance(adapter.model_digest, str) and adapter.model_digest, "digest del modello mancante"

    resp = adapter.complete("Rispondi solo con JSON.", '{"ping": 1}', temperature=0.0)
    assert isinstance(resp, LlmResponse)
    assert isinstance(resp.text, str)
    assert resp.tokens_in >= 0 and resp.tokens_out >= 0
