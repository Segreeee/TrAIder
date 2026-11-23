"""Adattatori finti delle porte: deterministici, senza rete né MT5. Usati da contratti e test d'integrazione."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd

from ports import CandidateRecord, JudgeInput, LlmResponse, NewsItem, Outcome, Position


class FakeMt5:
    """Sostituto del modulo MetaTrader5: barre nell'ORA DEL SERVER (UTC + offset_hours), come il vero MT5.
    Registra ogni chiamata a copy_rates_from_pos come (start, count)."""
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385

    _TF_SECONDS = {15: 900, 16385: 3600}

    def __init__(self, now: datetime, offset_hours: int = 2, ticks: dict | None = None, market_open: bool = True):
        self.now, self.offset, self.market_open = now, offset_hours, market_open
        self.ticks = ticks or {"EURUSD": (1.10000, 1.10008), "EURJPY": (160.000, 160.020), "EURGBP": (0.85000, 0.85010)}
        self.rate_calls: list[tuple[int, int]] = []
        self.sent, self.open_positions, self.deals = [], [], []
        self.equity, self.retcode = 1000.0, self.TRADE_RETCODE_DONE
        self.commission_per_lot_side = 0.0

    def symbol_select(self, symbol, enable):
        return True

    def copy_rates_from_pos(self, symbol, tf, start, count):
        self.rate_calls.append((start, count))
        step = self._TF_SECONDS[tf]
        server_now = int(self.now.timestamp()) + self.offset * 3600
        if not self.market_open:
            server_now -= 3 * 86400  # ultima barra di venerdì: vecchia rispetto ad adesso
        forming = server_now // step * step
        opens = forming - step * (start + np.arange(count)[::-1])
        rng = np.random.default_rng(len(self.rate_calls))
        close = 1.10 + np.cumsum(rng.normal(0, 0.0005, count))
        dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
                 ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")]
        rows = [(int(t), c, c + 0.0004, c - 0.0004, c, 100, 7, 0) for t, c in zip(opens, close, strict=True)]
        return np.array(rows, dtype=dtype)

    def symbol_info_tick(self, symbol):
        bid, ask = self.ticks[symbol]
        return SimpleNamespace(bid=bid, ask=ask, time=int(self.now.timestamp()))

    def last_error(self):
        return (0, "ok")

    # --- lato conto e ordini: le richieste finiscono in self.sent, nessun terminale coinvolto --- #
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, TRADE_ACTION_DEAL = 0, 1, 1
    ORDER_TIME_GTC, ORDER_FILLING_IOC, TRADE_RETCODE_DONE = 0, 1, 10009

    def order_send(self, request):
        self.sent.append(request)
        if self.retcode == self.TRADE_RETCODE_DONE:
            self.open_positions.append(SimpleNamespace(
                symbol=request["symbol"], type=request["type"], volume=request["volume"], price_open=request["price"],
                sl=request["sl"], tp=request["tp"], magic=request["magic"], ticket=len(self.sent), profit=0.0))
            self._deal(len(self.sent), 0, request["price"], request["volume"], request["magic"], 0.0, 0.0)
        return SimpleNamespace(retcode=self.retcode, price=request["price"], order=len(self.sent), comment="fake")

    def positions_get(self):
        return list(self.open_positions)

    def account_info(self):
        return SimpleNamespace(equity=self.equity)

    def history_deals_get(self, start=None, end=None, *, position=None):
        return [d for d in self.deals if position is None or getattr(d, "position_id", None) == position]

    def _deal(self, position, entry, price, volume, magic, profit, swap):
        self.deals.append(SimpleNamespace(position_id=position, entry=entry, price=price, volume=volume, magic=magic,
                                          profit=profit, swap=swap, commission=self.commission_per_lot_side * volume))

    def close_position(self, ticket, price, profit, swap=0.0):
        """Chiusura al broker (TP, SL o manuale): via dalle posizioni, deal di uscita nello storico."""
        (pos,) = [p for p in self.open_positions if p.ticket == ticket]
        self.open_positions.remove(pos)
        self._deal(ticket, 1, price, pos.volume, pos.magic, profit, swap)


class FakeLlm:
    """Risposte scriptate in ordine; un'eccezione nello script simula un errore di trasporto."""

    def __init__(self, script: list, model: str = "fake-llm", digest: str = "sha256:fake", tokens=(10, 5)):
        self.script, self.model, self.model_digest, self.tokens = list(script), model, digest, tokens
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, *, temperature: float) -> LlmResponse:
        self.calls.append({"system": system, "user": user, "temperature": temperature})
        item = self.script.pop(0) if self.script else '{"ping": 1}'
        if isinstance(item, Exception):
            raise item
        return LlmResponse(text=item, tokens_in=self.tokens[0], tokens_out=self.tokens[1])


class FakeMarketData:
    """Cammino casuale con seme fisso; restituisce solo candele chiuse rispetto a `now`
    (salvo include_forming=True, usato per provare che il contratto la rifiuta)."""

    def __init__(self, now: datetime, tf_minutes: int, seed: int = 1, include_forming: bool = False):
        self.now, self.tf, self.seed, self.include_forming = now, tf_minutes, seed, include_forming

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        tf = timedelta(minutes=self.tf)
        epoch = datetime(1970, 1, 1, tzinfo=self.now.tzinfo)
        forming_open = epoch + ((self.now - epoch) // tf) * tf
        last_open = forming_open if self.include_forming else forming_open - tf
        ts = pd.date_range(end=last_open, periods=count, freq=tf, tz="UTC")

        rng = np.random.default_rng(self.seed)
        close = 1.10 + np.cumsum(rng.normal(0, 0.0005, count))
        open_ = np.r_[close[0], close[:-1]]
        wick = np.abs(rng.normal(0, 0.0003, (2, count)))
        return pd.DataFrame({
            "timestamp": ts,
            "open": open_,
            "high": np.maximum(open_, close) + wick[0],
            "low": np.minimum(open_, close) - wick[1],
            "close": close,
            "volume": rng.integers(50, 500, count),
            "spread": np.full(count, 8),  # punti: 0.8 pip a 5 cifre
        })

    def eur_quote_rate(self, symbol: str) -> float:
        return 1.0 if symbol[3:6] == "EUR" else 1.10


class FakeNews:
    def __init__(self, now: datetime, items: list[NewsItem] | None = None):
        self.items = items if items is not None else [
            NewsItem("BCE lascia i tassi invariati", "fake", now - timedelta(hours=3), now - timedelta(hours=2)),
            NewsItem("Dati sull'occupazione USA sopra le attese", "fake", now - timedelta(hours=1), now - timedelta(minutes=30)),
        ]

    def latest(self, symbol: str, limit: int) -> list[NewsItem]:
        return sorted(self.items, key=lambda n: n.published_at, reverse=True)[:limit]


class FakeStore:
    """Archivio in memoria con gli stessi vincoli di unicità dello schema SQLite (D-007)."""

    def __init__(self):
        self.cycles: dict[int, tuple[str, datetime]] = {}
        self.llm_calls: list[tuple] = []
        self.candidates: dict[int, tuple[int, CandidateRecord]] = {}
        self.executions: list[tuple] = []
        self.broker_outcomes: dict[int, tuple] = {}
        self.veto_shadow: dict[int, bool] = {}
        self.outcomes: dict[int, Outcome] = {}
        self.finished: dict[int, dict] = {}

    def finish_cycle(self, cycle_id, status, error=None, input_json=None, code_version=None, config_hash=None):
        if cycle_id in self.finished or status not in ("done", "error"):
            raise ValueError(f"ciclo {cycle_id} già chiuso o status non valido: {status}")
        self.finished[cycle_id] = dict(status=status, error=error, input_json=input_json,
                                       code_version=code_version, config_hash=config_hash)

    def begin_cycle(self, symbol: str, candle_close_utc: datetime) -> int | None:
        if (symbol, candle_close_utc) in self.cycles.values():
            return None
        cycle_id = len(self.cycles) + 1
        self.cycles[cycle_id] = (symbol, candle_close_utc)
        return cycle_id

    def last_cycle(self, symbol: str) -> datetime | None:
        return max((c for s, c in self.cycles.values() if s == symbol), default=None)

    def record_llm_call(self, cycle_id: int, role: str, result) -> None:
        self.llm_calls.append((cycle_id, role, result))

    def record_candidate(self, cycle_id: int, record: CandidateRecord) -> int:
        if any(c == cycle_id and r.variant == record.variant for c, r in self.candidates.values()):
            raise ValueError(f"candidato già registrato per la variante {record.variant}")
        cid = len(self.candidates) + 1
        self.candidates[cid] = (cycle_id, record)
        return cid

    def record_execution(self, candidate_id: int, fill, lots: float, slippage_pips=None) -> None:
        self.executions.append((candidate_id, fill, lots, slippage_pips))

    def close(self) -> None:
        pass

    def judge_queue(self, variant):
        out = []
        for cycle, rec in self.candidates.values():
            done = self.finished.get(cycle, {}).get("status") == "done"
            if rec.variant == variant and done and cycle not in self.veto_shadow:
                views = {role: list(res.parsed.motivazioni) for c, role, res in self.llm_calls
                         if c == cycle and role in ("tecnico", "macro") and res.schema_valid}
                out.append(JudgeInput(cycle, rec, self.finished[cycle]["input_json"], views))
        return out

    def set_veto_shadow(self, cycle_id, veto):
        if cycle_id in self.veto_shadow:
            raise ValueError(f"veto_shadow del ciclo {cycle_id} già scritto")
        self.veto_shadow[cycle_id] = veto

    def open_sim_positions(self):
        out = []
        for cid, fill, lots, _ in self.executions:
            if fill.mode == "sim" and fill.accepted and cid not in self.outcomes:
                c = self.candidates[cid][1].candidate
                out.append(Position(c.symbol, c.direction, lots, fill.fill_price, c.sl, c.tp, fill.ticket))
        return out

    def open_broker_trades(self):
        return [(cid, self.candidates[cid][1], fill.ticket, lots, fill.fill_price)
                for cid, fill, lots, _ in self.executions
                if fill.mode == "mt5" and fill.accepted and cid not in self.broker_outcomes]

    def record_broker_outcome(self, candidate_id, closed, r_gross, r_net) -> bool:
        if candidate_id in self.broker_outcomes:
            return False
        self.broker_outcomes[candidate_id] = (closed, r_gross, r_net)
        return True

    def reconciliations(self):
        return [(cid, self.outcomes[cid].r_net, b[2]) for cid, b in sorted(self.broker_outcomes.items())
                if cid in self.outcomes and self.outcomes[cid].resolved_by == "virtuale"]

    def record_outcome(self, candidate_id: int, outcome: Outcome) -> bool:
        if candidate_id in self.outcomes:
            return False
        self.outcomes[candidate_id] = outcome
        return True

    def pending_candidates(self) -> list[tuple[int, CandidateRecord]]:
        return [(cid, r) for cid, (_, r) in self.candidates.items() if cid not in self.outcomes]

    def resolved(self, variant: str) -> list[tuple[CandidateRecord, Outcome]]:
        return [(r, self.outcomes[cid]) for cid, (_, r) in self.candidates.items()
                if r.variant == variant and cid in self.outcomes]