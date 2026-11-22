"""Contratto della porta SignalStore: gira sul FakeStore e (P3.19) sull'archivio SQLite.
`make_store` crea un archivio vuoto a ogni chiamata."""
from datetime import datetime, timedelta, timezone

import pytest

from domain.types import Candidate, Direction
from ports import CandidateRecord, Outcome

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
    store.record_llm_call(cycle, role="tecnico", result=object())
    cid = store.record_candidate(cycle, _record())
    store.record_execution(cid, fill=object(), lots=0.1)


ALL = [check_begin_cycle_idempotent, check_candidate_unique_per_variant, check_outcome_recorded_once,
       check_pending_excludes_resolved, check_llm_call_and_execution_are_kept]
