"""P3.19–P3.20: archivio SQLite (D-007). Stesso contratto del FakeStore, più vincoli dello schema
(chiavi esterne, CHECK), WAL sul file e sola aggiunta garantita da trigger."""
import sqlite3

import pytest

from adapters.sqlite_store import SqliteStore
from ports import Fill, LlmResult, SignalStore
from tests.contracts import store_contract
from tests.contracts.store_contract import CLOSE, _outcome, _record


def _memory():
    return SqliteStore(":memory:")


@pytest.mark.parametrize("check", store_contract.ALL, ids=lambda f: f.__name__)
def test_sqlite_store_honours_contract(check):
    check(_memory)


def test_sqlite_store_is_a_signal_store():
    assert isinstance(_memory(), SignalStore)


def test_foreign_keys_enforced():
    store = _memory()
    with pytest.raises(ValueError):
        store.record_candidate(999, _record())  # ciclo inesistente
    with pytest.raises(ValueError):
        store.record_outcome(999, _outcome())   # candidato inesistente


@pytest.mark.parametrize("sql", [
    "INSERT INTO cycles (symbol, candle_close_utc, started_at, status) VALUES ('EURUSD', 'x', 'y', 'FORSE')",
    "UPDATE candidates SET direction = 'LONG'",
    "UPDATE candidates SET final_action = 'MAYBE'",
])
def test_check_constraints_reject_bad_values(sql):
    store = _memory()
    store.record_candidate(store.begin_cycle("EURUSD", CLOSE), _record())
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(sql)


def test_bad_outcome_values_rejected():
    store = _memory()
    cid = store.record_candidate(store.begin_cycle("EURUSD", CLOSE), _record())
    bad = _outcome().__class__("MAYBE", None, None, None, "virtuale", CLOSE)
    with pytest.raises(ValueError):
        store.record_outcome(cid, bad)


def test_llm_call_columns_are_stored():
    store = _memory()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    store.record_llm_call(cycle, "tecnico", LlmResult(None, "raw", "qwen3:8b", "sha256:abc", "tecnico-v1",
                                                      812.5, 300, 20, 3, False, "schema: x"))
    row = store.conn.execute("SELECT role, model, model_digest, prompt_version, temperature, schema_valid, "
                             "attempts, tokens_in, error FROM llm_calls").fetchone()
    assert tuple(row) == ("tecnico", "qwen3:8b", "sha256:abc", "tecnico-v1", 0.0, 0, 3, 300, "schema: x")


# --- P3.20: WAL e sola aggiunta ---------------------------------------------- #


def test_wal_enabled_on_file_db(tmp_path):
    store = SqliteStore(str(tmp_path / "signals.db"))
    assert store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def _with_candidate():
    store = _memory()
    cycle = store.begin_cycle("EURUSD", CLOSE)
    cid = store.record_candidate(cycle, _record())
    return store, cycle, cid


def test_update_cycle_rejected():
    store, cycle, _ = _with_candidate()
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("UPDATE cycles SET candle_close_utc = 'altro' WHERE cycle_id = ?", (cycle,))


def test_running_cycle_can_be_closed_once():
    store, cycle, _ = _with_candidate()
    store.conn.execute("UPDATE cycles SET status = 'done', finished_at = 'fine' WHERE cycle_id = ?", (cycle,))
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("UPDATE cycles SET status = 'running' WHERE cycle_id = ?", (cycle,))


@pytest.mark.parametrize("table", ["cycles", "llm_calls", "candidates", "executions", "outcomes"])
def test_delete_rejected_everywhere(table):
    store, cycle, cid = _with_candidate()
    store.record_llm_call(cycle, "tecnico", LlmResult(None, "r", "m", "d", "v1", 1.0, 1, 1, 1, False, "e"))
    store.record_execution(cid, Fill("sim", True, 1.1, 0.0001, 1), 0.1)  # un DELETE senza righe non scatta
    store.record_outcome(cid, _outcome())
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(f"DELETE FROM {table}")


def test_delete_candidate_rejected():
    store, _, cid = _with_candidate()
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("DELETE FROM candidates WHERE candidate_id = ?", (cid,))


def test_veto_shadow_set_once_only():
    store, _, cid = _with_candidate()
    store.conn.execute("UPDATE candidates SET veto_shadow = 'veto' WHERE candidate_id = ?", (cid,))
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("UPDATE candidates SET veto_shadow = 'ok' WHERE candidate_id = ?", (cid,))


def test_other_candidate_columns_never_updated():
    store, _, cid = _with_candidate()
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("UPDATE candidates SET p = 0.9 WHERE candidate_id = ?", (cid,))


@pytest.mark.parametrize("sql", ["UPDATE outcomes SET r_net = 5", "UPDATE llm_calls SET model = 'x'",
                                 "UPDATE executions SET fill_price = 2"])
def test_outcomes_llm_calls_executions_never_updated(sql):
    store, cycle, cid = _with_candidate()
    store.record_llm_call(cycle, "tecnico", LlmResult(None, "r", "m", "d", "v1", 1.0, 1, 1, 1, False, "e"))
    store.record_execution(cid, Fill("sim", True, 1.1, 0.0001, 1), 0.1)
    store.record_outcome(cid, _outcome())
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(sql)
