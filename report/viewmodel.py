"""View-model della dashboard (P6.01): funzione pura archivio → dizionario, poi il rendering (P6.02) lo impagina.

Solo numeri dell'archivio: ultimi segnali della variante di produzione, posizioni simulate aperte ed esposizione
per valuta, curve di R netto e lordo, confronto tra varianti, calibrazione e copertura (dal report di P5.05).
La confidenza dichiarata dagli LLM non esiste nell'archivio e non entra qui.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from domain.exposure import currency_exposure
from evaluation.report import FINAL_MIN_CANDIDATES, FINAL_MIN_DAYS, PREREG_START, PRIMARY, analyze, load

_POSITIONS = """SELECT y.symbol, k.direction, e.lots, e.fill_price, k.sl, k.tp FROM executions e
                JOIN candidates k USING (candidate_id) JOIN cycles y USING (cycle_id)
                WHERE e.mode = 'sim' AND e.accepted = 1 AND y.candle_close_utc >= ?
                  AND e.candidate_id NOT IN (SELECT candidate_id FROM outcomes) ORDER BY e.candidate_id"""


@dataclass(frozen=True)
class Archive:
    rows: list[dict]
    cycles: list[dict]
    positions: list[dict]


def load_archive(db: Path, since: datetime = PREREG_START) -> Archive:
    """Lettura in sola lettura, come il report, dei soli cicli della preregistrazione (§1)."""
    rows, cycles = load(db, since=since)
    conn = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        positions = [dict(r) for r in conn.execute(_POSITIONS, (since.isoformat(),))]
    finally:
        conn.close()
    return Archive(rows, cycles, positions)


def viewmodel(a: Archive, production_variant: str = PRIMARY, last_n: int = 20) -> dict:
    prod = [r for r in a.rows if r["variant"] == production_variant]  # in ordine di chiusura
    signals = [{"time": r["candle_close_utc"], "symbol": r["symbol"], "direction": r["direction"], "p": r["p"],
                "p_star": r["p_star"], "ev": r["ev"], "decision": r["final_action"], "hold_reason": r["hold_reason"],
                "outcome": r["resolution"], "r_net": r["r_net"], "entry": r["entry_ref"], "sl": r["sl"], "tp": r["tp"],
                "lot": r["lot"]} for r in reversed(prod[-last_n:])]

    curve, net, gross = [], 0.0, 0.0
    for r in prod:
        if r["final_action"] == "TRADE" and r["resolution"] is not None:
            net, gross = net + r["r_net"], gross + r["r_gross"]
            curve.append({"time": r["candle_close_utc"], "net": net, "gross": gross})

    analysis = analyze(a.rows, a.cycles)
    variants = [{"name": name, "available": v["available"], "of": v["of"], "n": v["n"],
                 "bss": v["bss"][0] if v.get("bss") else None, "trades": v["trades"],
                 "mean_r_net_trade": v["mean_r_net_trade"][0] if v.get("mean_r_net_trade") else None}
                for name, v in analysis["variants"].items()]
    return {
        "production_variant": production_variant,
        "signals": signals,
        "positions": [{"symbol": p["symbol"], "direction": p["direction"], "lots": p["lots"], "entry": p["fill_price"],
                       "sl": p["sl"], "tp": p["tp"]} for p in a.positions],
        "exposure": {k: v for k, v in currency_exposure((p["symbol"], p["direction"]) for p in a.positions).items()
                     if v},
        "curve": curve,
        "variants": variants,
        "calibration": analysis["variants"][production_variant].get("calibration", []),
        "coverage": analysis["coverage"],
        "verdict": analysis["primary"]["verdict"],
        "final": analysis["primary"]["final"],
        "progress": {"n": analysis["primary"]["n"], "n_target": FINAL_MIN_CANDIDATES,
                     "days": analysis["primary"]["days"], "days_target": FINAL_MIN_DAYS},
        "last_cycle": max((c["candle_close_utc"] for c in a.cycles), default=None),
    }
