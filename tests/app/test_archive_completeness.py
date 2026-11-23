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
