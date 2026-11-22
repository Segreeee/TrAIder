"""P3.12: ogni output LLM passa da call_validated: schema pydantic, temperatura 0, retry limitati,
modello, digest e versione del prompt registrati nel risultato."""
from typing import Literal

from pydantic import BaseModel

from ports import Llm, call_validated
from tests.contracts.llm_contract import check_llm
from tests.fakes import FakeLlm


class Verdict(BaseModel):
    direzione: Literal["BUY", "SELL", "NEUTRAL"]


VALID = '{"direzione": "BUY"}'


def _call(llm, max_retries=2):
    return call_validated(llm, "sys", "user", Verdict, prompt_version="tecnico-v1", max_retries=max_retries)


def test_fake_llm_honours_contract():
    check_llm(FakeLlm([VALID]))
    assert isinstance(FakeLlm([VALID]), Llm)


def test_valid_output_parsed():
    res = _call(FakeLlm([VALID]))
    assert res.schema_valid and res.parsed == Verdict(direzione="BUY")
    assert res.attempts == 1 and res.raw == VALID


def test_invalid_then_valid_retries_once():
    res = _call(FakeLlm(['{"direzione": "FORSE"}', VALID]))
    assert res.schema_valid and res.attempts == 2


def test_gives_up_after_max_retries():
    llm = FakeLlm(["non json"] * 10)
    res = _call(llm, max_retries=2)
    assert not res.schema_valid and res.parsed is None
    assert res.attempts == 3 and len(llm.calls) == 3
    assert res.raw == "non json"


def test_transport_error_counts_as_failed_attempt():
    res = _call(FakeLlm([ConnectionError("ollama giù"), VALID]))
    assert res.schema_valid and res.attempts == 2


def test_transport_error_on_every_attempt_is_recorded():
    res = _call(FakeLlm([ConnectionError("ollama giù")] * 3), max_retries=2)
    assert not res.schema_valid and "ollama giù" in res.error


def test_temperature_zero_requested():
    llm = FakeLlm(['x', VALID])
    _call(llm)
    assert [c["temperature"] for c in llm.calls] == [0.0, 0.0]


def test_result_carries_model_digest_and_prompt_version():
    res = _call(FakeLlm([VALID], model="qwen-test", digest="sha256:abc"))
    assert (res.model, res.model_digest, res.prompt_version) == ("qwen-test", "sha256:abc", "tecnico-v1")


def test_tokens_and_latency_summed_over_attempts():
    res = _call(FakeLlm(["x", VALID], tokens=(100, 10)))
    assert (res.tokens_in, res.tokens_out) == (200, 20)
    assert res.latency_ms >= 0
