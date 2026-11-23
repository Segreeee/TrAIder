"""P3.32: cycles.input_json basta da solo a riprodurre candidato e decisioni, e non contiene segreti."""
import hashlib
import json
from datetime import timedelta

import pytest

from app.config import Settings
from app.replay import replay
from app.run_once import run_once
from domain.types import Candidate, Direction
from ports import CandidateRecord, Outcome
from tests.app.test_run_once import CLOSE, START, LosingBroker, _cfg, _ports, _quote
from tests.fakes import FakeStore


def _edge_store():
    # storico con il 70% di TP: il gate si apre e la variante di produzione fa TRADE
    store = FakeStore()
    for i in range(300):
        cycle = store.begin_cycle("EURUSD", START - timedelta(days=60) + timedelta(minutes=15 * i))
        cand = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, START - timedelta(days=60))
        for variant in ("v7-completo", "v2-tecnica"):
            cid = store.record_candidate(cycle, CandidateRecord(variant, cand, 1.0, 0.4, 0.42, 0.0, 0.0, "HOLD",
                                                                "GATE_EV", p0=0.4, features={}))
            store.record_outcome(cid, Outcome("TP" if i % 10 < 7 else "SL", None, None, None, "virtuale", START))
    return store


SCENARIOS = {
    "gate_chiuso": lambda: _ports(),
    "perdita_giornaliera": lambda: _ports(broker=LosingBroker(quote=_quote)),
    "trade": lambda: _ports(store=_edge_store()),
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_replay_from_input_json_gives_same_decision(scenario):
    ports = SCENARIOS[scenario]()
    report = run_once("EURUSD", CLOSE, ports, _cfg())
    cycle = max(ports.store.finished)
    recorded = {r.variant: (r.decision, r.hold_reason) for c, r in ports.store.candidates.values() if c == cycle}

    cand, decisions = replay(ports.store.finished[cycle]["input_json"])

    assert cand == report.candidate
    assert decisions == recorded and recorded  # nessuna variante persa o aggiunta


def test_replay_without_candidate_gives_nothing():
    from tests.app.test_run_once import TableMarket
    ports = _ports(market=TableMarket(h1_step=-0.0004))
    run_once("EURUSD", CLOSE, ports, _cfg())
    assert replay(ports.store.finished[1]["input_json"]) == (None, {})


def test_input_json_contains_no_secrets():
    cfg = Settings(_env_file=None, mt5_login="LOGIN-4242", mt5_password="pw-segreta-1", mt5_server="SRV-demo-9",
                   news_provider="finnhub", finnhub_api_key="fh-segreta-2", remote_judge_base_url="https://x",
                   remote_judge_model="m", remote_judge_api_key="rj-segreta-3")
    ports = _ports()
    run_once("EURUSD", CLOSE, ports, cfg)
    raw = ports.store.finished[1]["input_json"]
    for leaked in ("LOGIN-4242", "pw-segreta-1", "SRV-demo-9", "fh-segreta-2", "rj-segreta-3"):
        assert leaked not in raw
    assert json.loads(raw)["config"]["risk_per_trade_pct"] == cfg.risk_per_trade_pct


def test_input_json_has_market_and_account_inputs():
    ports = _ports()
    run_once("EURUSD", CLOSE, ports, _cfg())
    snap = json.loads(ports.store.finished[1]["input_json"])
    assert snap["eur_quote_rate"] == 1.10 and snap["pip_value_eur"] > 0 and snap["cost_pips"] >= 0
    assert "spread" in snap["bars_m15"][-1] and len(snap["bars_htf"]) > 0
    assert set(snap["account"]) == {"equity", "open_positions", "day_pnl"}


def test_input_hash_stable():
    def digest():
        ports = _ports()
        run_once("EURUSD", CLOSE, ports, _cfg())
        return hashlib.sha256(ports.store.finished[1]["input_json"].encode()).hexdigest()
    assert digest() == digest()


# --- P3.33: completezza di llm_calls e candidates sull'archivio SQLite vero (in memoria) --- #

from hypothesis import given, settings as hsettings, strategies as st  # noqa: E402

from adapters.sim_broker import SimBroker  # noqa: E402
from adapters.sqlite_store import SqliteStore  # noqa: E402
from ports import AccountState, NewsItem  # noqa: E402
from tests.app.test_run_once import TableMarket  # noqa: E402
from tests.fakes import FakeLlm  # noqa: E402

VIEW = '{"direzione": 1, "forza": 2, "orizzonte": "intraday", "motivazioni": ["x"]}'
NEWS = NewsItem("BCE invariata", "x", CLOSE - timedelta(hours=2), CLOSE - timedelta(hours=1))
GATE_REACHED = {None, "SAME_SYMBOL", "MAX_POSITIONS", "EXPOSURE", "LOT_BELOW_MIN"}


class AccountBroker(SimBroker):
    """Conto scelto dal test: capitale, posizioni aperte del bot e P&L del giorno."""

    def __init__(self, equity, positions, day_pnl):
        super().__init__(quote=_quote, equity=equity)
        self._extra, self._pnl = list(positions), day_pnl

    def account(self):
        own = super().account()
        return AccountState(own.equity, own.open_positions + self._extra, self._pnl)


def _with_history(store):
    # 70% di TP su 300 esiti: la Beta apre il gate (vedi test_edge_in_history_submits_production_only)
    for i in range(300):
        cycle = store.begin_cycle("EURUSD", START - timedelta(days=60) + timedelta(minutes=15 * i))
        cand = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, START - timedelta(days=60))
        for variant in ("v1-p0", "v2-tecnica", "v3-llm-tecnico", "v4-llm-macro", "v5-consenso", "v7-completo"):
            cid = store.record_candidate(cycle, CandidateRecord(variant, cand, 1.0, 0.4, 0.42, 0.0, 0.0, "HOLD",
                                                                "GATE_EV", p0=0.4, p5=0.3, lot=0.0, features={}))
            store.record_outcome(cid, Outcome("TP" if i % 10 < 7 else "SL", None, None, None, "virtuale", START))
        store.finish_cycle(cycle, "done")
    return store


def _run(trend_up, edge, tech_ok, macro_ok, news, equity, positions, losing):
    store = SqliteStore(":memory:")
    if edge:
        _with_history(store)
    llm = lambda ok: FakeLlm([VIEW] * 5 if ok else ['{"rotto": 1}'] * 5)  # noqa: E731
    ports = _ports(market=TableMarket(h1_step=0.0004 if trend_up else -0.0004), news_items=[NEWS] if news else [],
                   tech=llm(tech_ok), macro=llm(macro_ok), store=store,
                   broker=AccountBroker(equity, positions, -0.05 * equity if losing else 0.0))
    report = run_once("EURUSD", CLOSE, ports, Settings(_env_file=None, account_balance=equity))
    cycle = store.conn.execute("SELECT max(cycle_id) FROM cycles").fetchone()[0]
    return report, store, cycle


def _rows(store, sql, cycle):
    cur = store.conn.execute(sql, (cycle,))
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


@hsettings(max_examples=40, deadline=None)
@given(trend_up=st.booleans(), edge=st.booleans(), tech_ok=st.booleans(), macro_ok=st.booleans(),
       news=st.booleans(), equity=st.sampled_from([5.0, 10_000.0]), losing=st.booleans(),
       positions=st.lists(st.sampled_from([("EURUSD", "SELL"), ("GBPUSD", "BUY"), ("USDJPY", "BUY"),
                                           ("AUDUSD", "SELL")]), unique=True, max_size=4))
def test_every_cycle_has_complete_record(trend_up, edge, tech_ok, macro_ok, news, equity, positions, losing):
    report, store, cycle = _run(trend_up, edge, tech_ok, macro_ok, news, equity, positions, losing)
    (cyc,) = _rows(store, "SELECT * FROM cycles WHERE cycle_id = ?", cycle)
    assert cyc["status"] == "done" and cyc["input_json"] and cyc["input_hash"] and cyc["config_hash"]

    calls = _rows(store, "SELECT * FROM llm_calls WHERE cycle_id = ?", cycle)
    expected = [] if report.candidate is None or losing else ["tecnico"] + (["macro"] if news else [])
    assert sorted(c["role"] for c in calls) == sorted(expected)
    for c in calls:  # anche le chiamate non valide sono complete
        assert c["prompt_text"] and "EURUSD" in c["prompt_text"]
        assert c["model"] and c["model_digest"] and c["prompt_version"] and c["attempts"] >= 1
        assert bool(c["schema_valid"]) == (c["error"] is None)

    rows = _rows(store, "SELECT * FROM candidates WHERE cycle_id = ?", cycle)
    assert (report.candidate is None) == (rows == [])
    for r in rows:
        for col in ("p0", "p", "p5", "p_star", "ev", "ev5", "lot", "final_action"):
            assert r[col] is not None, col
        assert (r["hold_reason"] is None) == (r["final_action"] == "TRADE")
        assert (r["lot"] > 0) == (r["final_action"] == "TRADE")
        assert r["gate_passed"] == (None if r["hold_reason"] in ("LLM_INVALID", "DAILY_LOSS")
                                    else int(r["hold_reason"] in GATE_REACHED))
    executed = _rows(store, "SELECT e.* FROM executions e JOIN candidates k USING (candidate_id) WHERE k.cycle_id = ?",
                     cycle)
    assert len(executed) == (report.decision == "TRADE")


@pytest.mark.parametrize("kwargs, reason", [
    (dict(edge=False), "GATE_EV"),
    (dict(losing=True), "DAILY_LOSS"),
    (dict(tech_ok=False), "LLM_INVALID"),
    (dict(positions=[("EURUSD", "SELL")]), "SAME_SYMBOL"),
    (dict(positions=[("GBPUSD", "BUY")]), "EXPOSURE"),
    (dict(equity=5.0), "LOT_BELOW_MIN"),
    (dict(), None),
])
def test_each_hold_reason_reachable(kwargs, reason):
    # gli scenari della proprietà esistono davvero: ognuno produce il suo motivo sulla variante di produzione
    args = dict(trend_up=True, edge=True, tech_ok=True, macro_ok=True, news=False, equity=10_000.0, positions=[],
                losing=False) | kwargs
    report, _, _ = _run(**args)
    assert report.hold_reason == reason and report.decision == ("TRADE" if reason is None else "HOLD")


def test_invalid_llm_output_recorded():
    _, store, cycle = _run(True, False, False, True, False, 10_000.0, [], False)
    (call,) = _rows(store, "SELECT * FROM llm_calls WHERE cycle_id = ?", cycle)
    assert call["schema_valid"] == 0 and call["parsed_json"] is None
    assert call["response_raw"] == '{"rotto": 1}' and call["error"].startswith("schema")
    assert call["attempts"] == _cfg().llm_max_retries + 1 and "EURUSD" in call["prompt_text"]
