"""Archivio SQLite che implementa la porta SignalStore (D-007). Il file sta in data/, ignorato da git."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from domain.types import Candidate, Direction
from ports import CandidateRecord, ClosedTrade, Fill, LlmResult, Outcome, Position

SCHEMA = Path(__file__).with_name("schema.sql")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _gate_passed(hold_reason: Optional[str]) -> Optional[int]:
    """NULL se la decisione si è fermata prima del gate (LLM non valido, perdita giornaliera)."""
    if hold_reason in ("LLM_INVALID", "DAILY_LOSS"):
        return None
    return int(hold_reason != "GATE_EV")


class SqliteStore:
    def __init__(self, path: str, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")  # la dashboard legge mentre il demone scrive; in :memory: resta memory
        self.conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        self._clock = clock

    def close(self) -> None:
        self.conn.close()

    def _insert(self, sql: str, params: tuple) -> sqlite3.Cursor:
        """Una transazione per scrittura; i vincoli violati diventano ValueError come nella porta."""
        try:
            with self.conn:
                return self.conn.execute(sql, params)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"archivio: {exc}") from exc

    def begin_cycle(self, symbol: str, candle_close_utc: datetime) -> Optional[int]:
        with self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO cycles (symbol, candle_close_utc, started_at) VALUES (?, ?, ?)",
                (symbol, _iso(candle_close_utc), _iso(self._clock())))
        return cur.lastrowid if cur.rowcount == 1 else None

    def finish_cycle(self, cycle_id: int, status: str, error: Optional[str] = None, input_json: Optional[str] = None,
                     code_version: Optional[str] = None, config_hash: Optional[str] = None) -> None:
        if status not in ("done", "error"):
            raise ValueError(f"archivio: status di chiusura non valido: {status}")
        input_hash = hashlib.sha256(input_json.encode()).hexdigest() if input_json else None
        try:
            with self.conn:
                cur = self.conn.execute(
                    "UPDATE cycles SET status = ?, error = ?, input_json = ?, input_hash = ?, code_version = ?,"
                    " config_hash = ?, finished_at = ? WHERE cycle_id = ?",
                    (status, error, input_json, input_hash, code_version, config_hash, _iso(self._clock()), cycle_id))
        except sqlite3.IntegrityError as exc:  # trigger (già chiuso) o CHECK (status non valido)
            raise ValueError(f"archivio: {exc}") from exc
        if cur.rowcount != 1:
            raise ValueError(f"archivio: ciclo {cycle_id} inesistente")

    def last_cycle(self, symbol: str) -> Optional[datetime]:
        row = self.conn.execute("SELECT MAX(candle_close_utc) FROM cycles WHERE symbol = ?", (symbol,)).fetchone()
        return datetime.fromisoformat(row[0]) if row[0] else None

    def record_llm_call(self, cycle_id: int, role: str, result: LlmResult) -> None:
        parsed = result.parsed.model_dump_json() if result.parsed is not None else None
        self._insert(
            "INSERT INTO llm_calls (cycle_id, role, model, model_digest, prompt_version, prompt_text, temperature,"
            " response_raw, parsed_json, schema_valid, attempts, latency_ms, tokens_in, tokens_out, error)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cycle_id, role, result.model, result.model_digest, result.prompt_version, result.prompt or None,
             result.raw, parsed, int(result.schema_valid), result.attempts, result.latency_ms, result.tokens_in,
             result.tokens_out, result.error or None))

    def record_candidate(self, cycle_id: int, record: CandidateRecord) -> int:
        c = record.candidate
        cur = self._insert(
            "INSERT INTO candidates (cycle_id, variant, direction, entry_ref, sl, tp, d_sl, d_tp, cost_pips, p, p_star,"
            " ev, ev5, final_action, hold_reason, p0, p5, lot, gate_passed, features_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cycle_id, record.variant, c.direction.value, c.entry, c.sl, c.tp, c.d_sl, c.d_tp, record.cost_pips,
             record.p, record.p_star, record.ev, record.ev5, record.decision, record.hold_reason,
             record.p0, record.p5, record.lot, _gate_passed(record.hold_reason), json.dumps(record.features)))
        assert cur.lastrowid is not None  # sempre valorizzato dopo un INSERT riuscito
        return cur.lastrowid

    def record_execution(self, candidate_id: int, fill: Fill, lots: float,
                         slippage_pips: Optional[float] = None) -> None:
        self._insert(
            "INSERT INTO executions (candidate_id, mode, accepted, ticket, lots, fill_price, spread, slippage,"
            " commission, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (candidate_id, fill.mode, int(fill.accepted), fill.ticket, lots, fill.fill_price, fill.spread,
             slippage_pips, fill.commission, fill.reason or None))

    def open_sim_positions(self) -> list[Position]:
        rows = self.conn.execute(
            "SELECT y.symbol, k.direction, e.lots, e.fill_price, k.sl, k.tp, e.ticket FROM executions e"
            " JOIN candidates k USING (candidate_id) JOIN cycles y USING (cycle_id)"
            " WHERE e.mode = 'sim' AND e.accepted = 1"
            " AND e.candidate_id NOT IN (SELECT candidate_id FROM outcomes) ORDER BY e.candidate_id").fetchall()
        return [Position(s, Direction(d), lots, price, sl, tp, ticket) for s, d, lots, price, sl, tp, ticket in rows]

    def open_broker_trades(self) -> list[tuple[int, CandidateRecord, int, float, float]]:
        rows = self.conn.execute(
            f"SELECT {self._RECORD_COLUMNS}, e.ticket, e.lots, e.fill_price FROM executions e"
            " JOIN candidates k USING (candidate_id) JOIN cycles y USING (cycle_id)"
            " WHERE e.mode = 'mt5' AND e.accepted = 1"
            " AND e.candidate_id NOT IN (SELECT candidate_id FROM broker_outcomes) ORDER BY e.candidate_id").fetchall()
        return [(r[0], self._to_record(r), r[-3], r[-2], r[-1]) for r in rows]

    def record_broker_outcome(self, candidate_id: int, closed: ClosedTrade, r_gross: float, r_net: float) -> bool:
        if self.conn.execute("SELECT 1 FROM broker_outcomes WHERE candidate_id = ?", (candidate_id,)).fetchone():
            return False
        self._insert(
            "INSERT INTO broker_outcomes (candidate_id, detected_utc, exit_price, profit_eur, commission_eur, swap_eur,"
            " r_gross, r_net) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (candidate_id, _iso(self._clock()), closed.exit_price, closed.profit_eur, closed.commission_eur,
             closed.swap_eur, r_gross, r_net))
        return True

    def reconciliations(self) -> list[tuple[int, float, float]]:
        return [tuple(r) for r in self.conn.execute(
            "SELECT b.candidate_id, o.r_net, b.r_net FROM broker_outcomes b JOIN outcomes o USING (candidate_id)"
            " WHERE o.resolved_by = 'virtuale' ORDER BY b.candidate_id")]

    def record_outcome(self, candidate_id: int, outcome: Outcome) -> bool:
        if self.conn.execute("SELECT 1 FROM outcomes WHERE candidate_id = ?", (candidate_id,)).fetchone():
            return False
        self._insert(
            "INSERT INTO outcomes (candidate_id, resolution, exit_utc, exit_price, r_gross, r_net, resolved_by)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (candidate_id, outcome.result, _iso(outcome.resolved_at), outcome.exit_price, outcome.r_gross,
             outcome.r_net, outcome.resolved_by))
        return True

    _RECORD_COLUMNS = ("k.candidate_id, k.variant, y.symbol, k.direction, k.entry_ref, k.sl, k.tp, y.candle_close_utc,"
                       " k.cost_pips, k.p, k.p_star, k.ev, k.ev5, k.final_action, k.hold_reason, k.p0, k.p5, k.lot,"
                       " k.features_json")

    @staticmethod
    def _to_record(r) -> CandidateRecord:
        return CandidateRecord(
            variant=r[1], candidate=Candidate(r[2], Direction(r[3]), r[4], r[5], r[6], datetime.fromisoformat(r[7])),
            cost_pips=r[8], p=r[9], p_star=r[10], ev=r[11], ev5=r[12], decision=r[13], hold_reason=r[14],
            p0=r[15], p5=r[16], lot=r[17], features=json.loads(r[18]) if r[18] else {})

    def pending_candidates(self) -> list[tuple[int, CandidateRecord]]:
        rows = self.conn.execute(
            f"SELECT {self._RECORD_COLUMNS} FROM candidates k JOIN cycles y USING (cycle_id)"
            " WHERE k.candidate_id NOT IN (SELECT candidate_id FROM outcomes) ORDER BY k.candidate_id").fetchall()
        return [(r[0], self._to_record(r)) for r in rows]

    def resolved(self, variant: str) -> list[tuple[CandidateRecord, Outcome]]:
        rows = self.conn.execute(
            f"SELECT {self._RECORD_COLUMNS}, o.resolution, o.exit_price, o.r_net, o.r_gross, o.resolved_by, o.exit_utc"
            " FROM candidates k JOIN cycles y USING (cycle_id) JOIN outcomes o USING (candidate_id)"
            " WHERE k.variant = ? ORDER BY k.candidate_id", (variant,)).fetchall()
        return [(self._to_record(r), Outcome(r[19], r[20], r[21], r[22], r[23], datetime.fromisoformat(r[24])))
                for r in rows]