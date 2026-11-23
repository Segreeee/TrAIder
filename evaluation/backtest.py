"""Backtest walk-forward delle varianti senza LLM (D-008, P5.06): v1-p0 e v2-tecnica.

Per ogni candela chiusa: stessa finestra di barre del demone (CANDLES_COUNT M15, 120 H1), stesso generatore
di candidati, stesso stimatore (`app.variants.estimate`) con il solo storico già risolto a quella chiusura
(walk-forward: nessun esito del futuro), stessa decisione, stesso simulatore di esito (`virtual_outcome`).
Scrive in un archivio SQLite separato, che il report di P5.05 legge come quello del demone.

Limiti (ponytail): conto piatto (capitale configurato, nessuna posizione aperta, P&L del giorno 0), quindi
le decisioni misurano il gate EV e il lotto, non esposizione e limite giornaliero; cambio EUR costante.
Con lo storico oltre MIN_TRADES_FOR_MODEL la logistica si rifà a ogni candela come nel demone: su decine di
migliaia di barre è lenta; se serve, rifit ogni N candele (cambia il walk-forward: va dichiarato).
Uso con MT5 aperto (solo dati, nessun ordine): python -m evaluation.backtest --symbol EURUSD --bars 20000
"""
import argparse
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from app.candidates import M15, generate
from app.config import Settings
from app.decide import Context, decide
from app.resolve import virtual_outcome
from app.run_once import HTF_BARS
from app.variants import VARIANTS, estimate
from domain.costs import cost_pips
from domain.pip import pip_size, pip_value_eur
from domain.probability import p0
from ports import CandidateRecord, Outcome, SignalStore

H1 = timedelta(hours=1)
NO_LLM = ("v1-p0", "v2-tecnica")


def run_backtest(symbol: str, m15: pd.DataFrame, h1: pd.DataFrame, store: SignalStore, cfg: Settings,
                 eur_quote_rate: float, variants: tuple[str, ...] = NO_LLM, code_version: str = "backtest") -> int:
    """Restituisce quante candele hanno prodotto un candidato (cicli archiviati)."""
    llm = [v for v in variants if {"tecnico", "macro"} & set(VARIANTS[v].features + VARIANTS[v].needs)]
    if llm:
        raise ValueError(f"varianti con LLM {llm}: si valutano solo in avanti (D-008), mai in backtest")

    pip = pip_size(symbol)
    pip_value = pip_value_eur(symbol, eur_quote_rate)
    # come app/run_once: le distanze partono dal prezzo di esecuzione, c = commissione + slippage (T-010)
    cost = cost_pips(0.0, pip / 10, pip, cfg.commission_eur_per_lot or 0.0, pip_value, cfg.slippage_pips)
    ctx = Context(cfg.account_balance, [], 0.0, cost, pip_value, cfg)
    done: dict[str, list[tuple[CandidateRecord, Outcome]]] = {v: [] for v in variants}
    cycles = 0

    for i in range(cfg.candles_count - 1, len(m15)):
        close = m15["timestamp"].iloc[i].to_pydatetime() + M15
        bars = m15.iloc[i - cfg.candles_count + 1:i + 1].reset_index(drop=True)
        htf = h1[h1["timestamp"] + H1 <= close].tail(HTF_BARS).reset_index(drop=True)
        generated = generate(symbol, bars, htf, close)
        if generated is None:
            continue
        cand, features = generated
        cycle = store.begin_cycle(symbol, close)
        if cycle is None:
            continue  # candela già nel backtest (rilancio sullo stesso archivio)
        cycles += 1
        for name in variants:
            history = [(r, o) for r, o in done[name] if o.resolved_at <= close]  # solo il passato
            est = estimate(VARIANTS[name], cand, features, history, cfg)
            d = decide(cand, est, ctx)
            rec = CandidateRecord(name, cand, cost, est.p, d.p_star, d.ev, d.ev5, d.decision,
                                  d.hold_reason.value if d.hold_reason else None,
                                  p0=p0(cand.d_sl, cand.d_tp), p5=est.p5, lot=d.lot, features=dict(features))
            cid = store.record_candidate(cycle, rec)
            outcome = virtual_outcome(rec, m15, cfg.horizon_bars)
            if outcome is not None:
                store.record_outcome(cid, outcome)
                done[name].append((rec, outcome))
        store.finish_cycle(cycle, "done", None, json.dumps({"backtest": True, "eur_quote_rate": eur_quote_rate}),
                           code_version, cfg.config_hash())
    return cycles


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - richiede il terminale MT5
    parser = argparse.ArgumentParser(description="Backtest walk-forward delle varianti senza LLM (solo dati MT5)")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--bars", type=int, default=20000, help="barre M15 di storico")
    parser.add_argument("--db", type=Path, help="archivio di uscita (default: data/backtest_<simbolo>.db)")
    args = parser.parse_args(argv)

    import MetaTrader5 as mt5  # solo qui, come in main.py

    from adapters.mt5_data import Mt5Data
    from adapters.sqlite_store import SqliteStore
    from app.compose import mt5_init_kwargs

    cfg = Settings()
    if not mt5.initialize(**mt5_init_kwargs(cfg)):
        print(f"MetaTrader5 non inizializzato: {mt5.last_error()}")
        return 1
    try:
        data = Mt5Data(mt5)
        m15 = data.closed_bars(args.symbol, "M15", args.bars)
        h1 = data.closed_bars(args.symbol, "H1", args.bars // 4 + HTF_BARS)
        store = SqliteStore(str(args.db or Path(f"data/backtest_{args.symbol}.db")))
        try:
            n = run_backtest(args.symbol, m15, h1, store, cfg, data.eur_quote_rate(args.symbol))
        finally:
            store.close()
        print(f"{n} candidati archiviati; report: python -m evaluation.report --db {args.db or f'data/backtest_{args.symbol}.db'}")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
