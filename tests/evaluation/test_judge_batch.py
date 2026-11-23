"""P5.08 / D-018: lotto offline del giudice esterno. Mai un'API vera nei test: solo FakeLlm."""
from datetime import timedelta

from app.config import Settings
from app.run_once import run_once
from evaluation.judge_batch import REPEATS, in_sample, run_judge_batch
from ports import NewsItem
from tests.app.test_run_once import CLOSE, _ports
from tests.fakes import FakeLlm

VETO = '{"veto": true, "checks": [{"id": "direzione_coerente", "passed": false, "evidence": "trend contrario"}]}'
NEWS = NewsItem("BCE invariata", "x", CLOSE - timedelta(hours=2), CLOSE - timedelta(hours=1))


def _cfg(pct=100):
    return Settings(_env_file=None, remote_judge_sample_pct=pct)


def _archived_cycle():
    ports = _ports(news_items=[NEWS])
    run_once("EURUSD", CLOSE, ports, _cfg())
    return ports.store


def _judge_calls(store):
    return [(role, result) for _, role, result in store.llm_calls if role.startswith("giudice")]


def test_batch_sets_veto_once():
    store = _archived_cycle()
    judge = FakeLlm([VETO] * 20, model="giudice-esterno")
    assert run_judge_batch(store, judge, _cfg()) == 1
    assert set(store.veto_shadow.values()) == {True}
    calls = len(judge.calls)
    assert run_judge_batch(store, judge, _cfg()) == 0 and len(judge.calls) == calls  # già giudicato


def test_repetitions_and_swapped_order_recorded():
    store = _archived_cycle()
    judge = FakeLlm([VETO] * 20, model="giudice-esterno")
    run_judge_batch(store, judge, _cfg())
    roles = [role for role, _ in _judge_calls(store)]
    assert roles == ["giudice"] * REPEATS + ["giudice-inverso", "giudice-ruoli"]
    prompts = [c["user"] for c in judge.calls]
    assert prompts[0] == prompts[1] == prompts[2]            # ripetizioni identiche: misurano la stabilità
    assert prompts[3] != prompts[0]                           # ordine dei pareri invertito
    assert "tecnico" in prompts[4] and "tecnico" not in prompts[0]  # ruoli nominati solo nella prova del bias
    assert "BCE invariata" in prompts[0]                      # notizie incluse (D-018)
    assert all(c["temperature"] == 0 for c in judge.calls)


def test_invalid_verdicts_leave_candidate_for_next_batch():
    store = _archived_cycle()
    judge = FakeLlm(['{"veto": "forse"}'] * 30, model="giudice-esterno")
    assert run_judge_batch(store, judge, _cfg()) == 0
    assert store.veto_shadow == {} and all(not r.schema_valid for _, r in _judge_calls(store))


def test_remote_sample_skipped_when_unconfigured():
    store = _archived_cycle()
    assert run_judge_batch(store, None, _cfg()) == 0
    assert _judge_calls(store) == []


def test_remote_sample_is_20pct_seeded():
    chosen = {i for i in range(1, 5001) if in_sample(i, 20)}
    assert 0.18 < len(chosen) / 5000 < 0.22
    assert chosen == {i for i in range(1, 5001) if in_sample(i, 20)}  # deterministico
    assert chosen != {i for i in range(1, 5001) if in_sample(i, 20, seed=1)}
    assert not any(in_sample(i, 0) for i in range(1, 500)) and all(in_sample(i, 100) for i in range(1, 500))


def test_unsampled_candidate_is_not_judged():
    store = _archived_cycle()
    judge = FakeLlm([VETO] * 20, model="giudice-esterno")
    assert run_judge_batch(store, judge, _cfg(pct=0)) == 0 and judge.calls == []
