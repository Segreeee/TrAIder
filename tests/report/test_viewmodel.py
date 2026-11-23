"""P6.01: view-model della dashboard (D-009), funzione pura archivio → dizionario. Numeri calcolati a mano."""
from datetime import datetime, timedelta, timezone

import pytest

from adapters.sqlite_store import SqliteStore
from domain.types import Candidate, Direction
from ports import CandidateRecord, Fill, Outcome
from report.viewmodel import load_archive, viewmodel

T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)


def _cycle(store, symbol, close, decision, outcome=None, execute=False):
    cycle = store.begin_cycle(symbol, close)
    pip = 0.01 if symbol.endswith("JPY") else 0.0001
    entry = 150.0 if symbol.endswith("JPY") else 1.1
    cand = Candidate(symbol, Direction.BUY, entry, entry - 20 * pip, entry + 30 * pip, close)
    for variant, p in (("v7-completo", 0.47), ("v2-tecnica", 0.41)):
        trade = decision == "TRADE" and variant == "v7-completo"
        cid = store.record_candidate(cycle, CandidateRecord(
            variant, cand, 1.0, p, 0.42, 0.1 if trade else -0.05, 0.02, "TRADE" if trade else "HOLD",
            None if trade else "GATE_EV", p0=0.4, p5=p - 0.04, lot=0.1 if trade else 0.0, features={}))
        if trade and execute:
            store.record_execution(cid, Fill("sim", True, entry, 0.00008, cid, commission=-0.35), 0.1, 0.0)
        if outcome:
            win = outcome == "TP"
            store.record_outcome(cid, Outcome(outcome, None, 1.45 if win else -1.05, 1.5 if win else -1.0,
                                              "virtuale", close + 2 * H))
    store.finish_cycle(cycle, "done", input_json="{}", config_hash="h1")


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "a.db"
    store = SqliteStore(str(path))
    _cycle(store, "EURUSD", T0, "TRADE", "TP", execute=True)
    _cycle(store, "GBPUSD", T0 + H, "TRADE", "SL", execute=True)
    _cycle(store, "USDJPY", T0 + 2 * H, "HOLD")
    _cycle(store, "EURUSD", T0 + 3 * H, "TRADE", execute=True)  # ancora aperta
    store.close()
    return path


def test_viewmodel_on_fake_archive_hand_computed(db):
    vm = viewmodel(load_archive(db), production_variant="v7-completo", last_n=3)

    assert [(s["symbol"], s["decision"], s["hold_reason"], s["outcome"]) for s in vm["signals"]] == [
        ("EURUSD", "TRADE", None, None), ("USDJPY", "HOLD", "GATE_EV", None), ("GBPUSD", "TRADE", None, "SL")]
    assert vm["signals"][0]["p"] == pytest.approx(0.47) and vm["signals"][0]["p_star"] == pytest.approx(0.42)

    # curve dei TRADE risolti della variante di produzione, in ordine di chiusura: 1.45, 1.45 − 1.05
    assert [round(c["net"], 2) for c in vm["curve"]] == [1.45, 0.40]
    assert [round(c["gross"], 2) for c in vm["curve"]] == [1.5, 0.5]

    assert [(p["symbol"], p["direction"]) for p in vm["positions"]] == [("EURUSD", "BUY")]
    assert vm["exposure"] == {"EUR": 1, "USD": -1}

    assert vm["coverage"]["cycles_done"] == 4 and vm["coverage"]["resolved"] == 2
    v7 = next(v for v in vm["variants"] if v["name"] == "v7-completo")
    assert (v7["n"], v7["trades"]) == (2, 2) and v7["mean_r_net_trade"] == pytest.approx(0.2)
    assert vm["production_variant"] == "v7-completo" and vm["verdict"] == "non concludente"


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_no_llm_confidence_in_viewmodel(db):
    vm = viewmodel(load_archive(db), production_variant="v7-completo")
    assert not [k for k in _keys(vm) if "confiden" in k.lower()]


def test_viewmodel_of_empty_archive(tmp_path):
    path = tmp_path / "vuoto.db"
    SqliteStore(str(path)).close()
    vm = viewmodel(load_archive(path), production_variant="v7-completo")
    assert vm["signals"] == [] and vm["curve"] == [] and vm["positions"] == [] and vm["exposure"] == {}
