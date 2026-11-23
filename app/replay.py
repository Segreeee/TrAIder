"""Replay di un ciclo dal solo cycles.input_json (P3.32): stesso candidato, stesse decisioni per variante.

Le stime p/p5 sono un input (dipendono dallo storico risolto al momento del ciclo, che poi cresce);
tutto il resto si ricalcola: candidato dalle candele grezze, contesto da conto e costi, decisione da decide().
"""
import json
from datetime import datetime
from typing import Optional

import pandas as pd

from app.candidates import generate
from app.config import Settings
from app.decide import Context, decide
from app.variants import Estimate
from domain.types import Candidate


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def replay(input_json: str) -> tuple[Optional[Candidate], dict[str, tuple[str, Optional[str]]]]:
    s = json.loads(input_json)
    cfg = Settings.model_construct(**s["config"])  # già validata quando il ciclo è stato eseguito
    generated = generate(s["symbol"], _frame(s["bars_m15"]), _frame(s["bars_htf"]),
                         datetime.fromisoformat(s["candle_close_utc"]))
    if generated is None:
        return None, {}
    cand, a = generated[0], s["account"]
    ctx = Context(a["equity"], [tuple(p) for p in a["open_positions"]], a["day_pnl"], s["cost_pips"],
                  s["pip_value_eur"], cfg)
    decisions = {}
    for name, v in s["variants"].items():
        d = decide(cand, Estimate(**v["estimate"]), ctx, llm_invalid=v["llm_invalid"])
        decisions[name] = (d.decision, d.hold_reason.value if d.hold_reason else None)
    return cand, decisions
