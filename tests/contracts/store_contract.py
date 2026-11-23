"""Contratto della porta SignalStore: gira sul FakeStore e (P3.19) sull'archivio SQLite.
`make_store` crea un archivio vuoto a ogni chiamata."""
from datetime import datetime, timedelta, timezone

import pytest

from domain.types import Candidate, Direction
from ports import CandidateRecord, ClosedTrade, Fill, LlmResult, Outcome

CLOSE = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)


def _record(variant="v1-tecnico", close=CLOSE):
    cand = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, close)
    return CandidateRecord(variant=variant, candidate=cand, cost_pips=1.0, p=0.4, p_star=0.42,
                           ev=-0.05, ev5=-0.2, decision="HOLD", hold_reason="GATE_EV",
                           p0=0.4, p5=0.31, lot=0.0, features={"momentum": 1.5, "tecnico": None})


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


def check_resolved_history_per_variant(make_store):
    store = make_store()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    a = store.record_candidate(cycle, _record("v1"))
    store.record_candidate(cycle, _record("v2"))
    assert store.resolved("v1") == []
    store.record_outcome(a, _outcome())
    assert store.resolved("v1") == [(_record("v1"), _outcome())]
    assert store.resolved("v2") == []


def check_broker_outcome_beside_virtual(make_store):
    # P3.34: l'esito del broker non sostituisce quello virtuale, gli sta accanto
    store = make_store()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    sim, real = store.record_candidate(cycle, _record("v1")), store.record_candidate(cycle, _record("v2"))
    store.record_execution(sim, Fill("sim", True, 1.10008, 0.00008, 1, commission=-0.35), lots=0.1, slippage_pips=0.0)
    store.record_execution(real, Fill("mt5", True, 1.10010, 0.00008, 7, commission=-0.35), lots=0.1, slippage_pips=0.2)
    assert [(cid, ticket, lots, price) for cid, _, ticket, lots, price in store.open_broker_trades()] == [
        (real, 7, 0.1, 1.10010)]

    closed = ClosedTrade(exit_price=1.0980, profit_eur=-19.1, commission_eur=-0.70, swap_eur=-0.20)
    assert store.record_broker_outcome(real, closed, r_gross=-1.0, r_net=-1.05) is True
    assert store.record_broker_outcome(real, closed, r_gross=-1.0, r_net=-1.05) is False
    assert store.open_broker_trades() == []
    assert store.reconciliations() == []  # manca ancora l'esito virtuale
    store.record_outcome(real, _outcome())
    assert store.reconciliations() == [(real, _outcome().r_net, -1.05)]


def check_open_sim_positions(make_store):
    # R4 / D-016: eseguiti in simulazione e non ancora risolti; rifiutati ed esecuzioni MT5 esclusi
    store = make_store()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    sim, refused, real = (store.record_candidate(cycle, _record(v)) for v in ("v1", "v2", "v3"))
    store.record_execution(sim, Fill("sim", True, 1.10008, 0.00008, 1), lots=0.1)
    store.record_execution(refused, Fill("sim", False, 0.0, 0.00008, None, "lotto"), lots=0.1)
    store.record_execution(real, Fill("mt5", True, 1.10008, 0.00008, 9), lots=0.1)
    (pos,) = store.open_sim_positions()
    assert (pos.symbol, pos.direction, pos.lots, pos.entry, pos.sl, pos.tp) == (
        "EURUSD", Direction.BUY, 0.1, 1.10008, 1.0980, 1.1030)
    store.record_outcome(sim, _outcome())
    assert store.open_sim_positions() == []


def check_judge_queue_and_veto_once(make_store):
    # P5.08: coda del giudice per la variante scelta, con input, motivazioni valide e veto scritto una volta
    from app.extractors import AnalystView
    store = make_store()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    a = store.record_candidate(cycle, _record("v7-completo"))
    store.record_candidate(cycle, _record("v2-tecnica"))
    view = AnalystView(direzione=1, forza=2, orizzonte="intraday", motivazioni=["trend al rialzo"])
    store.record_llm_call(cycle, "tecnico", LlmResult(view, "{}", "m", "d", "v1", 1.0, 1, 1, 1, True))
    store.record_llm_call(cycle, "macro", LlmResult(None, "rotto", "m", "d", "v1", 1.0, 1, 1, 3, False, "schema"))
    store.finish_cycle(cycle, "done", input_json='{"htf_trend": "rialzista"}')
    (item,) = store.judge_queue("v7-completo")
    assert (item.cycle_id, item.record, item.input_json) == (cycle, _record("v7-completo"), '{"htf_trend": "rialzista"}')
    assert item.views == {"tecnico": ["trend al rialzo"]}  # le chiamate non valide non danno pareri
    store.set_veto_shadow(cycle, True)
    assert store.judge_queue("v7-completo") == []
    with pytest.raises(ValueError):
        store.set_veto_shadow(cycle, False)
    assert a is not None


ALL = [check_finish_cycle_once, check_resolved_history_per_variant, check_begin_cycle_idempotent,
       check_candidate_unique_per_variant, check_outcome_recorded_once, check_pending_excludes_resolved,
       check_llm_call_and_execution_are_kept, check_pending_roundtrip_keeps_the_record,
       check_broker_outcome_beside_virtual, check_open_sim_positions, check_judge_queue_and_veto_once]
