"""Contratto della porta SignalStore: gira sul FakeStore e (P3.19) sull'archivio SQLite.
`make_store` crea un archivio vuoto a ogni chiamata."""
from datetime import datetime, timedelta, timezone

import pytest

from domain.types import Candidate, Direction
from ports import CandidateRecord, Fill, LlmResult, Outcome

CLOSE = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)


def _record(variant="v1-tecnico", close=CLOSE):
    cand = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, close)
    return CandidateRecord(variant=variant, candidate=cand, cost_pips=1.0, p=0.4, p_star=0.42,
                           ev=-0.05, ev5=-0.2, decision="HOLD", hold_reason="GATE_EV")


def _outcome():
    return Outcome("SL", 1.0980, r_net=-1.05, r_gross=-1.0, resolved_by="virtuale",
                   resolved_at=CLOSE + timedelta(hours=3))


def check_begin_cycle_idempotent(make_store):
    store = make_store()
    assert store.begin_cycle("EURUSD", CLOSE) is not None
    assert store.begin_cycle("EURUSD", CLOSE) is None, "stessa candela elaborata due volte"
    assert store.begin_cycle("GBPUSD", CLOSE) is not None
    assert store.last_cycle("EURUSD") == CLOSE


def check_candidate_unique_per_variant(make_store):
    store = make_store()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    store.record_candidate(cycle, _record("v1"))
    store.record_candidate(cycle, _record("v2"))
    with pytest.raises(ValueError):
        store.record_candidate(cycle, _record("v1"))


def check_outcome_recorded_once(make_store):
    store = make_store()
    cid = store.record_candidate(store.begin_cycle("EURUSD", CLOSE), _record())
    assert store.record_outcome(cid, _outcome()) is True
    assert store.record_outcome(cid, _outcome()) is False, "esito scritto due volte"


def check_pending_excludes_resolved(make_store):
    store = make_store()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    a = store.record_candidate(cycle, _record("v1"))
    b = store.record_candidate(cycle, _record("v2"))
    store.record_outcome(a, _outcome())
    assert [cid for cid, _ in store.pending_candidates()] == [b]


def check_llm_call_and_execution_are_kept(make_store):
    store = make_store()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    result = LlmResult(None, "non json", "qwen3:8b", "sha256:abc", "tecnico-v1", 812.5, 300, 20, 3, False, "schema: x")
    store.record_llm_call(cycle, role="tecnico", result=result)
    cid = store.record_candidate(cycle, _record())
    store.record_execution(cid, fill=Fill("sim", True, 1.10008, 0.00008, 1), lots=0.1)


def check_pending_roundtrip_keeps_the_record(make_store):
    store = make_store()
    rec = _record()
    cid = store.record_candidate(store.begin_cycle("EURUSD", CLOSE), rec)
    assert store.pending_candidates() == [(cid, rec)]


def check_finish_cycle_once(make_store):
    store = make_store()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    store.finish_cycle(cycle, "done", input_json='{"a": 1}', code_version="abc", config_hash="h")
    with pytest.raises(ValueError):
        store.finish_cycle(cycle, "error", error="seconda chiusura")
    with pytest.raises(ValueError):
        store.finish_cycle(store.begin_cycle("GBPUSD", CLOSE), "forse")


ALL = [check_finish_cycle_once,check_begin_cycle_idempotent, check_candidate_unique_per_variant, check_outcome_recorded_once,
       check_pending_excludes_resolved, check_llm_call_and_execution_are_kept,
       check_pending_roundtrip_keeps_the_record]
