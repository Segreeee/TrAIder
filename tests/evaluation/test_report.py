"""P5.05: report dall'archivio (preregistrazione §4-§6). Archivio finto con p note: ogni numero del report
si confronta con lo stesso calcolo fatto qui sui dati generati."""
import hashlib
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from adapters.sqlite_store import SqliteStore
from domain.types import Candidate, Direction
from evaluation.bootstrap import session_of
from evaluation.metrics import brier_skill
from evaluation.report import analyze, load, main, render
from ports import CandidateRecord, Outcome

T0 = datetime(2026, 12, 1, tzinfo=timezone.utc)
W, L = 1.45, 1.05  # d_SL 20, d_TP 30, costo 1 pip


def _rec(variant, cand, p, trade):
    ev = p * W - (1 - p) * L
    return CandidateRecord(variant, cand, 1.0, p, 0.42, ev, ev - 0.05, "TRADE" if trade else "HOLD",
                           None if trade else "GATE_EV", p0=0.4, p5=p - 0.05, lot=0.1 if trade else 0.0, features={})


def _archive(path, days=40, per_day=5, seed=3, with_macro=False):
    store = SqliteStore(str(path), clock=lambda: T0)
    rng = np.random.default_rng(seed)
    truth = []
    for d in range(days):
        for k in range(per_day):
            close = T0 + timedelta(days=d, hours=5 * k)
            symbol = "EURUSD" if k % 2 == 0 else "GBPUSD"
            cycle = store.begin_cycle(symbol, close)
            p_true, p_tech = float(rng.uniform(0.2, 0.7)), float(np.clip(0.4 + rng.normal(0, 0.1), 0.05, 0.95))
            win = bool(rng.random() < p_true)
            cand = Candidate(symbol, Direction.BUY, 1.1000, 1.0980, 1.1030, close)
            ps = {"v1-p0": 0.4, "v2-tecnica": p_tech, "v7-completo": p_true}
            if with_macro and k == 0:
                ps["v4-llm-macro"] = p_true
            for variant, p in ps.items():
                trade = variant != "v1-p0" and p > 0.5
                cid = store.record_candidate(cycle, _rec(variant, cand, p, trade))
                store.record_outcome(cid, Outcome("TP" if win else "SL", None, W if win else -L, 1.5 if win else -1.0,
                                                  "virtuale", close + timedelta(hours=1)))
            store.finish_cycle(cycle, "done", input_json="{}", config_hash="h1")
            truth.append((symbol, close, p_tech, p_true, win))
    # un ciclo in errore e un candidato ancora senza esito: entrano solo nella copertura
    store.finish_cycle(store.begin_cycle("EURUSD", T0 - timedelta(days=1)), "error", error="x", config_hash="h1")
    pending = store.begin_cycle("GBPUSD", T0 - timedelta(days=2))
    store.record_candidate(pending, _rec("v7-completo", Candidate("GBPUSD", Direction.BUY, 1.1, 1.098, 1.103,
                                                                    T0 - timedelta(days=2)), 0.45, False))
    store.finish_cycle(pending, "done", input_json="{}", config_hash="h1")
    store.close()
    return truth


def test_report_on_fake_archive_matches_expected_numbers(tmp_path):
    db = tmp_path / "a.db"
    truth = _archive(db)
    y = np.array([w for *_, w in truth], dtype=float)
    p_tech, p_true = np.array([t[2] for t in truth]), np.array([t[3] for t in truth])
    r = analyze(*load(db))

    assert r["coverage"] == {"cycles_done": 201, "cycles_error": 1, "resolved": 200, "pending": 1}
    v7, v2 = r["variants"]["v7-completo"], r["variants"]["v2-tecnica"]
    assert v7["n"] == v2["n"] == 200
    assert v7["bss"][0] == pytest.approx(brier_skill(y, p_true, np.full_like(y, 0.4)))
    assert v2["bss"][0] == pytest.approx(brier_skill(y, p_tech, np.full_like(y, 0.4)))
    traded = p_true > 0.5
    assert v7["trades"] == int(traded.sum())
    assert v7["mean_r_net_trade"][0] == pytest.approx(np.where(y[traded] == 1, W, -L).mean())

    delta, low, high = r["primary"]["delta_bss"]
    assert delta == pytest.approx(v7["bss"][0] - v2["bss"][0]) and low <= delta <= high
    assert r["primary"]["verdict"] in {"gli LLM aggiungono valore", "gli LLM peggiorano", "non concludente"}
    assert r["primary"]["final"] is False  # 200 < 300 candidati risolti: solo descrittivo

    sessions = {s for _, c, *_ in truth for s in [session_of(c)]}
    assert set(r["by_session"]) == sessions and set(r["by_symbol"]) == {"EURUSD", "GBPUSD"}
    assert sum(g["n"] for g in r["by_symbol"].values()) == 200

    text = render(r)
    assert f"{v7['bss'][0]:.3f}" in text and r["primary"]["verdict"] in text
    assert "solo descrittiv" in text


def test_unavailable_variants_reported_as_such(tmp_path):
    db = tmp_path / "a.db"
    _archive(db, days=5, with_macro=True)
    r = analyze(*load(db))
    assert r["variants"]["v4-llm-macro"]["available"] == 5 and r["variants"]["v4-llm-macro"]["of"] == 25
    assert r["variants"]["v5-consenso"]["available"] == 0
    text = render(r)
    assert "v5-consenso: non disponibile" in text and "v4-llm-macro: disponibile in 5 candidati su 25" in text


def test_report_reads_only(tmp_path):
    db = tmp_path / "a.db"
    _archive(db, days=3)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    render(analyze(*load(db)))
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    with pytest.raises(Exception):
        load(tmp_path / "non_esiste.db")  # in sola lettura non crea un archivio vuoto
    assert not (tmp_path / "non_esiste.db").exists()


def test_main_writes_markdown(tmp_path, capsys):
    db = tmp_path / "a.db"
    _archive(db, days=3)
    assert main(["--db", str(db)]) == 0
    assert "# Report" in capsys.readouterr().out
