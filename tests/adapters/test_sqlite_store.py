"""P3.19: archivio SQLite (D-007). Stesso contratto del FakeStore, più vincoli dello schema:
chiavi esterne attive e CHECK sui valori ammessi."""
import sqlite3

import pytest

from adapters.sqlite_store import SqliteStore
from ports import LlmResult, SignalStore
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
