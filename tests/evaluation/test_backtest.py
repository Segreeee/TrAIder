"""P5.06: backtest walk-forward solo per le varianti senza LLM (D-008), con lo stesso generatore, lo stesso
modello di probabilità e lo stesso simulatore di esito del demone."""
from datetime import timedelta

import pytest

from adapters.sqlite_store import SqliteStore
from app.config import Settings
from app.resolve import resolve_pending
from evaluation.backtest import run_backtest
from evaluation.report import analyze, load
from tests.app.test_run_once import START, _bars, _trend
from tests.fakes import FakeStore

M15 = _bars(_trend(500, 0.00005, 1.10), 15, START)
H1 = _bars(_trend(160, 0.0002, 1.095), 60, START - timedelta(hours=20))


def _cfg():
    # Beta soltanto: la logistica rifà fit e bootstrap a ogni candela (lenta) ed è provata in tests/app/test_variants.py
    return Settings(_env_file=None, commission_eur_per_lot=7.0, min_trades_for_model=10_000)


class _Market:
    def closed_bars(self, symbol, timeframe, count):
        return M15.tail(count).reset_index(drop=True)


def test_refuses_llm_variants():
    with pytest.raises(ValueError, match="solo in avanti"):
        run_backtest("EURUSD", M15, H1, SqliteStore(":memory:"), _cfg(), eur_quote_rate=1.10,
                     variants=("v2-tecnica", "v3-llm-tecnico"))


def test_synthetic_bars_known_outcomes():
    store = SqliteStore(":memory:")
    cycles = run_backtest("EURUSD", M15, H1, store, _cfg(), eur_quote_rate=1.10)
    assert cycles > 0
    rows = store.conn.execute(
        "SELECT k.variant, k.direction, o.resolution, o.r_net FROM candidates k JOIN outcomes o USING (candidate_id)"
    ).fetchall()
    assert rows and {v for v, *_ in rows} == {"v1-p0", "v2-tecnica"} and {d for _, d, *_ in rows} == {"BUY"}

    # stesso simulatore del demone: resolve_pending sugli stessi candidati dà gli stessi esiti
    live = FakeStore()
    expected = {}
    for cid, rec in store.pending_candidates() + [(cid, rec) for cid, rec in _resolved_records(store)]:
        new = live.record_candidate(live.begin_cycle(f"{rec.variant}-{cid}", rec.candidate.candle_close_utc), rec)
        expected[new] = cid
    resolve_pending(live, _Market(), M15["timestamp"].iloc[-1].to_pydatetime() + timedelta(minutes=15))
    archived = {cid: (res, r) for cid, res, r in store.conn.execute(
        "SELECT candidate_id, resolution, r_net FROM outcomes")}
    for new, cid in expected.items():
        if cid in archived:
            assert (live.outcomes[new].result, live.outcomes[new].r_net) == archived[cid]
        else:
            assert new not in live.outcomes  # nessun esito nemmeno dal demone (fine dei dati)


def _resolved_records(store):
    ids = [cid for (cid,) in store.conn.execute("SELECT candidate_id FROM outcomes")]
    recs = {cid: rec for cid, rec in _all_records(store)}
    return [(cid, recs[cid]) for cid in ids]


def _all_records(store):
    rows = store.conn.execute(f"SELECT {store._RECORD_COLUMNS} FROM candidates k JOIN cycles y USING (cycle_id)")
    return [(r[0], store._to_record(r)) for r in rows]


def test_walk_forward_no_future_fit(monkeypatch):
    import evaluation.backtest as bt
    seen = []
    real = bt.estimate

    def spy(variant, cand, features, history, cfg):
        seen.append((cand.candle_close_utc, [o.resolved_at for _, o in history]))
        return real(variant, cand, features, history, cfg)

    monkeypatch.setattr(bt, "estimate", spy)
    run_backtest("EURUSD", M15, H1, SqliteStore(":memory:"), _cfg(), eur_quote_rate=1.10)
    assert seen and all(t <= close for close, ts in seen for t in ts)  # mai un esito del futuro
    assert any(ts for _, ts in seen)  # e lo storico passato viene davvero usato


def test_report_reads_the_backtest_archive(tmp_path):
    db = tmp_path / "backtest.db"
    store = SqliteStore(str(db))
    run_backtest("EURUSD", M15, H1, store, _cfg(), eur_quote_rate=1.10)
    store.close()
    r = analyze(*load(db))
    assert r["variants"]["v1-p0"]["n"] > 0 and r["variants"]["v2-tecnica"]["n"] == r["variants"]["v1-p0"]["n"]
    assert r["variants"]["v7-completo"]["available"] == 0  # le varianti LLM non esistono nel backtest
