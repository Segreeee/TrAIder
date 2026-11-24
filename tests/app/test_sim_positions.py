"""R4 / D-016: le posizioni del broker simulato non si chiudevano mai (dopo 3 trade ogni candidato andava
in HOLD MAX_POSITIONS). Ora sono i candidati eseguiti in simulazione e non ancora risolti, letti
dall'archivio: si chiudono con l'esito virtuale e sopravvivono ai riavvii."""
from adapters.sim_broker import SimBroker
from adapters.sqlite_store import SqliteStore
from app.config import Settings
from app.run_once import run_once
from domain.types import Direction
from ports import Outcome
from tests.app.test_archive_completeness import _with_history
from tests.app.test_run_once import CLOSE, _ports, _quote


def _sim(store):
    return SimBroker(quote=_quote, open_positions=store.open_sim_positions)


def test_sim_position_closes_with_virtual_outcome_and_survives_restart():
    store = _with_history(SqliteStore(":memory:"))
    broker = _sim(store)
    report = run_once("EURUSD", CLOSE, _ports(store=store, broker=broker), Settings(_env_file=None))
    assert report.decision == "TRADE"
    assert broker.account().open_positions == [("EURUSD", "BUY")]

    restarted = _sim(store)  # processo nuovo: la posizione è ancora aperta
    (pos,) = restarted.positions()
    assert (pos.symbol, pos.direction) == ("EURUSD", Direction.BUY) and pos.lots > 0

    (cid,) = [cid for cid, *_ in store.conn.execute(
        "SELECT candidate_id FROM executions WHERE mode = 'sim' AND accepted = 1")]
    store.record_outcome(cid, Outcome("TP", pos.tp, 1.4, 1.5, "virtuale", CLOSE))
    assert restarted.account().open_positions == [] and restarted.positions() == []
