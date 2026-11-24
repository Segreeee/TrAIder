"""P3.17: adattatore LLM su client OpenAI-compatibile (Ollama in locale, fornitore remoto a scelta, Q-001).
Il client è iniettato: nessuna rete nei test."""
from types import SimpleNamespace

import pytest

from adapters.llm_openai import OpenAiLlm, build_client
from tests.contracts.llm_contract import check_llm

SECRET = "sk-test-0123456789abcdef"


class FakeClient:
    def __init__(self, content='{"ok": true}', usage=(120, 30), error: Exception | None = None):
        self.kwargs: list[dict] = []
        self._content, self._usage, self._error = content, usage, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs.append(kwargs)
        if self._error:
            raise self._error
        usage = SimpleNamespace(prompt_tokens=self._usage[0], completion_tokens=self._usage[1]) if self._usage else None
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))], usage=usage)


def _llm(client, **kw):
    return OpenAiLlm(client, model="qwen3:8b", model_digest="sha256:abc", **kw)


def test_openai_llm_honours_contract():
    check_llm(_llm(FakeClient()))


def test_think_block_stripped():
    # porting di test_think_block_is_stripped_before_json_parse
    raw = '<think>ragiono...\n{"action": "SELL"}</think>\n{"action":"BUY"}'
    assert _llm(FakeClient(content=raw)).complete("s", "u", temperature=0.0).text == '{"action":"BUY"}'


def test_temperature_zero_seed_and_json_mode_sent():
    client = FakeClient()
    _llm(client, seed=7).complete("sys", "user", temperature=0.0)
    kw = client.kwargs[0]
    assert kw["temperature"] == 0.0 and kw["seed"] == 7
    assert kw["response_format"] == {"type": "json_object"} and kw["model"] == "qwen3:8b"
    assert kw["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}]


def test_usage_recorded_and_missing_usage_is_zero():
    assert _llm(FakeClient(usage=(120, 30))).complete("s", "u", temperature=0.0).tokens_in == 120
    resp = _llm(FakeClient(usage=None)).complete("s", "u", temperature=0.0)
    assert (resp.tokens_in, resp.tokens_out) == (0, 0)


def test_empty_content_is_empty_text():
    assert _llm(FakeClient(content=None)).complete("s", "u", temperature=0.0).text == ""


def test_digest_required():
    with pytest.raises(ValueError):
        OpenAiLlm(FakeClient(), model="qwen3:8b", model_digest="")


def test_no_default_remote_base_url():
    with pytest.raises(TypeError):
        build_client(api_key=SECRET)  # base_url obbligatorio: nessun fornitore remoto implicito
    with pytest.raises(ValueError):
        build_client(base_url="", api_key=SECRET)


def test_api_key_not_in_error_messages():
    err = ConnectionError(f"401 Unauthorized: invalid key {SECRET}")
    llm = _llm(FakeClient(error=err), secrets=(SECRET,))
    with pytest.raises(RuntimeError) as info:
        llm.complete("s", "u", temperature=0.0)
    assert SECRET not in str(info.value) and "***" in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__  # niente catena con la chiave
