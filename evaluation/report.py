"""Report della preregistrazione (docs/PREREGISTRAZIONE.md, §4-§6) dall'archivio, in sola lettura.

    python -m evaluation.report --db data/traider.db [--out report.md]

load: legge l'archivio (connessione SQLite in sola lettura); analyze: numeri (funzione pura); render: markdown.
Si analizza una sola serie, l'ultima per config_hash (§7); le altre si elencano con il loro conteggio.
"""
import argparse
import io
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from app.variants import VARIANTS
from evaluation.bootstrap import cluster_ci, groups, session_of
from evaluation.metrics import auc, brier, brier_skill, calibration_deciles, log_loss, max_drawdown

PRIMARY, BASELINE = "v7-completo", "v2-tecnica"
FINAL_MIN_CANDIDATES, FINAL_MIN_DAYS = 300, 30
VERDICTS = ("gli LLM aggiungono valore", "gli LLM peggiorano", "non concludente")

_ROWS = """SELECT k.cycle_id, y.symbol, y.candle_close_utc, y.config_hash, k.variant, k.p, k.p0, k.final_action,
                  o.resolution, o.r_net, o.r_gross
           FROM candidates k JOIN cycles y USING (cycle_id) LEFT JOIN outcomes o USING (candidate_id)
           ORDER BY y.candle_close_utc, k.cycle_id"""


def load(db: Path, since: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """(righe candidato × variante con l'esito virtuale, cicli), solo con chiusura della candela ≥ `since`
    (§1: i dati della preregistrazione partono dal commit di approvazione). Sola lettura: non crea né modifica."""
    conn = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(_ROWS)]
        cycles = [dict(r) for r in conn.execute(
            "SELECT cycle_id, status, config_hash, candle_close_utc FROM cycles ORDER BY cycle_id")]
    finally:
        conn.close()
    if since is not None:
        rows = [r for r in rows if datetime.fromisoformat(r["candle_close_utc"]) >= since]
        cycles = [c for c in cycles if datetime.fromisoformat(c["candle_close_utc"]) >= since]
    return rows, cycles


def _bss_ci(y: np.ndarray, p: np.ndarray, p0: np.ndarray, days: list) -> tuple[float, float, float]:
    return cluster_ci(lambda i: brier_skill(y[i], p[i], p0[i]), days)


def _variant(name: str, rows: list[dict], n_resolved: int) -> dict:
    """Disponibilità contata sui candidati con esito, come tutte le metriche."""
    out: dict = {"available": sum(r["resolution"] is not None for r in rows), "of": n_resolved, "n": 0}
    decided = [r for r in rows if r["resolution"] in ("TP", "SL")]
    if decided:
        y = np.array([r["resolution"] == "TP" for r in decided], dtype=float)
        p, p0 = np.array([r["p"] for r in decided]), np.array([r["p0"] for r in decided])
        days = [r["candle_close_utc"][:10] for r in decided]
        out.update(n=len(decided), brier=brier(y, p), bss=_bss_ci(y, p, p0, days), log_loss=log_loss(y, p),
                   auc=auc(y, p), calibration=calibration_deciles(y, p))
    trades = [r for r in rows if r["final_action"] == "TRADE" and r["resolution"] is not None]
    out["trades"] = len(trades)
    if trades:
        r_net = np.array([r["r_net"] for r in trades], dtype=float)
        out.update(mean_r_net_trade=cluster_ci(lambda i: float(r_net[i].mean()), [r["candle_close_utc"][:10] for r in trades]),
                   total_r_net=float(r_net.sum()), total_r_gross=float(sum(r["r_gross"] for r in trades)),
                   drawdown=max_drawdown(list(r_net)))
    return out


def _primary(by_cycle: dict[int, dict[str, dict]], n_days: int) -> dict:
    pairs = [(v[PRIMARY], v[BASELINE]) for v in by_cycle.values()
             if PRIMARY in v and BASELINE in v and v[PRIMARY]["resolution"] in ("TP", "SL")]
    out: dict = {"n": len(pairs), "days": n_days, "delta_bss": None, "delta_r": None}
    if pairs:
        y = np.array([a["resolution"] == "TP" for a, _ in pairs], dtype=float)
        pa, pb = np.array([a["p"] for a, _ in pairs]), np.array([b["p"] for _, b in pairs])
        p0 = np.array([a["p0"] for a, _ in pairs])
        days = [a["candle_close_utc"][:10] for a, _ in pairs]
        out["delta_bss"] = cluster_ci(lambda i: brier_skill(y[i], pa[i], p0[i]) - brier_skill(y[i], pb[i], p0[i]), days)

        resolved = [(v[PRIMARY], v[BASELINE]) for v in by_cycle.values()
                    if PRIMARY in v and BASELINE in v and v[PRIMARY]["resolution"] is not None]
        ta = np.array([a["final_action"] == "TRADE" for a, _ in resolved])
        tb = np.array([b["final_action"] == "TRADE" for _, b in resolved])
        if ta.any() and tb.any():
            ra = np.array([a["r_net"] for a, _ in resolved], dtype=float)
            rb = np.array([b["r_net"] for _, b in resolved], dtype=float)

            def delta_r(i: np.ndarray) -> float:  # nan se nel campione una variante non ha TRADE
                a, b = ra[i][ta[i]], rb[i][tb[i]]
                return float(a.mean() - b.mean()) if len(a) and len(b) else float("nan")

            out["delta_r"] = cluster_ci(delta_r, [a["candle_close_utc"][:10] for a, _ in resolved])

    bss, dr = out["delta_bss"], out["delta_r"]
    if bss is not None and bss[1] > 0 and dr is not None and not dr[2] < 0:
        out["verdict"] = VERDICTS[0]
    elif bss is not None and bss[2] < 0:
        out["verdict"] = VERDICTS[1]
    else:
        out["verdict"] = VERDICTS[2]  # anche quando ΔR non è calcolabile (nessun TRADE): non si conclude
    out["final"] = out["n"] >= FINAL_MIN_CANDIDATES and n_days >= FINAL_MIN_DAYS
    return out


def _descriptive(rows: list[dict], key) -> dict:
    """Solo descrittivo (§4): variante di produzione per simbolo o per sessione."""
    decided = [r for r in rows if r["variant"] == PRIMARY and r["resolution"] in ("TP", "SL")]
    out = {}
    for label, idx in groups([key(r) for r in decided]).items():
        sub = [decided[i] for i in idx]
        y = np.array([r["resolution"] == "TP" for r in sub], dtype=float)
        p, p0 = np.array([r["p"] for r in sub]), np.array([r["p0"] for r in sub])
        out[label] = {"n": len(sub), "tp_rate": float(y.mean()), "p_mean": float(p.mean()),
                      "bss": brier_skill(y, p, p0)}
    return out


def analyze(rows: list[dict], cycles: list[dict]) -> dict:
    series = Counter(c["config_hash"] for c in cycles)
    latest = cycles[-1]["config_hash"] if cycles else None
    rows = [r for r in rows if r["config_hash"] == latest]
    cycles = [c for c in cycles if c["config_hash"] == latest]

    by_cycle: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by_cycle[r["cycle_id"]][r["variant"]] = r
    resolved = sum(any(v["resolution"] is not None for v in vs.values()) for vs in by_cycle.values())
    days = {r["candle_close_utc"][:10] for r in rows if r["resolution"] in ("TP", "SL")}

    return {
        "series": latest, "other_series": {h: n for h, n in series.items() if h != latest},
        "coverage": {"cycles_done": sum(c["status"] == "done" for c in cycles),
                     "cycles_error": sum(c["status"] == "error" for c in cycles),
                     "resolved": resolved, "pending": len(by_cycle) - resolved},
        "variants": {name: _variant(name, [r for r in rows if r["variant"] == name], resolved)
                     for name in VARIANTS},
        "primary": _primary(by_cycle, len(days)),
        "by_symbol": _descriptive(rows, lambda r: r["symbol"]),
        "by_session": _descriptive(rows, lambda r: session_of(datetime.fromisoformat(r["candle_close_utc"]))),
    }


def _ci(t) -> str:
    return "—" if t is None else f"{t[0]:.3f} [{t[1]:.3f}, {t[2]:.3f}]"


def _num(x) -> str:
    return "—" if x is None else f"{x:.3f}"


def render(r: dict) -> str:
    c, pr = r["coverage"], r["primary"]
    lines = [
        "# Report della valutazione in avanti", "",
        f"Serie analizzata (config_hash): `{r['series']}`."
        + (f" Altre serie, non mescolate: {r['other_series']}." if r["other_series"] else ""), "",
        "## Copertura", "",
        f"Cicli completati {c['cycles_done']}, in errore {c['cycles_error']}; "
        f"candidati con esito {c['resolved']}, in attesa {c['pending']}.", "",
        f"## Metrica primaria: {PRIMARY} contro {BASELINE}", "",
        f"Candidati appaiati con esito TP/SL: {pr['n']} in {pr['days']} giorni.",
        f"- ΔBSS (IC 95% per giorno): {_ci(pr['delta_bss'])}",
        f"- Δ R netto medio sui TRADE: {_ci(pr['delta_r'])}",
        f"- Esito secondo la §6: **{pr['verdict']}**",
        "" if pr["final"] else
        f"- Analisi solo descrittiva: l'analisi finale richiede almeno {FINAL_MIN_CANDIDATES} candidati "
        f"e {FINAL_MIN_DAYS} giorni.", "",
        "## Varianti", "",
        "| Variante | n TP/SL | Brier | BSS vs p0 [IC 95%] | log-loss | AUC | TRADE | R netto medio TRADE [IC] | R netto / lordo | drawdown |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    notes = []
    for name, v in r["variants"].items():
        if v["available"] == 0:
            notes.append(f"- {name}: non disponibile (nessun candidato con i requisiti)")
            continue
        if v["available"] < v["of"]:
            notes.append(f"- {name}: disponibile in {v['available']} candidati su {v['of']} (con esito)")
        totals = f"{v['total_r_net']:.2f} / {v['total_r_gross']:.2f}" if v["trades"] else "—"
        lines.append(f"| {name} | {v['n']} | {_num(v.get('brier'))} | {_ci(v.get('bss'))} | {_num(v.get('log_loss'))} | "
                     f"{_num(v.get('auc'))} | {v['trades']} | {_ci(v.get('mean_r_net_trade'))} | {totals} | "
                     f"{_num(v.get('drawdown'))} |")
    lines += ["", *notes, "", f"## Calibrazione di {PRIMARY} (gruppi di pari numerosità)", "",
              "| p media | TP osservati | n |", "|---|---|---|"]
    lines += [f"| {b['p_mean']:.3f} | {b['y_rate']:.3f} | {b['n']} |" for b in r["variants"][PRIMARY].get("calibration", [])]
    for title, key in (("simbolo", "by_symbol"), ("sessione", "by_session")):
        lines += ["", f"## Per {title} ({PRIMARY}, solo descrittivo)", "", "| | n | TP | p media | BSS |", "|---|---|---|---|---|"]
        lines += [f"| {k} | {g['n']} | {g['tp_rate']:.3f} | {g['p_mean']:.3f} | {g['bss']:.3f} |" for k, g in r[key].items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report della valutazione in avanti (sola lettura)")
    parser.add_argument("--db", type=Path, default=Path("data/traider.db"))
    parser.add_argument("--out", type=Path, help="file markdown di uscita (default: stampa a video)")
    parser.add_argument("--dal", type=datetime.fromisoformat,
                        help="solo cicli con chiusura da questo istante, con fuso (es. 2026-11-23T16:45:00+00:00)")
    args = parser.parse_args(argv)
    text = render(analyze(*load(args.db, since=args.dal)))
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        if isinstance(sys.stdout, io.TextIOWrapper):  # il terminale Windows (cp1252) non ha "Δ"
            sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
