"""Rendering della dashboard (P6.02, D-009): view-model → HTML statico, offline, una colonna per il telefono.

Grafici in SVG inline (niente librerie né URL esterni): tooltip nativi con <title>, etichette dirette a fine
linea, valori anche nel testo. Tutto il testo che viene dall'archivio passa da html.escape.
"""
import os
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from string import Template

from evaluation.report import PRIMARY
from report.viewmodel import load_archive, viewmodel

TEMPLATE = Template((Path(__file__).parent / "template.html").read_text(encoding="utf-8"))
STALE_AFTER = timedelta(minutes=30)  # due candele senza cicli: il demone è fermo

VERDICT = {"non concludente": "Ancora non concludente",
           "gli LLM aggiungono valore": "Gli LLM aggiungono valore",
           "gli LLM peggiorano": "Gli LLM peggiorano la stima"}
HOLD = {"GATE_EV": "vantaggio insufficiente", "DAILY_LOSS": "limite di perdita giornaliera",
        "SAME_SYMBOL": "già aperta sul simbolo", "EXPOSURE": "esposizione per valuta",
        "MAX_POSITIONS": "troppe posizioni aperte", "LOT_BELOW_MIN": "lotto sotto il minimo",
        "LLM_INVALID": "risposta LLM non valida", "NO_CANDIDATE": "nessun candidato"}


def _digits(symbol: str) -> int:
    """Decimali dei prezzi MT5: 3 per le coppie JPY, 5 per le altre (come le quotazioni da copiare)."""
    return 3 if symbol.upper().endswith("JPY") else 5


def _t(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")


def _signed(x: float) -> str:
    return f"{x:+.2f}".replace("-", "−")


def _meter(label: str, value: int, target: int) -> str:
    pct = min(100.0, 100.0 * value / target) if target else 0.0
    return (f'<div class="meter"><div class="meter-label"><span>{label}</span><span>{value} su {target}</span></div>'
            f'<div class="meter-track" role="progressbar" aria-label="{label}" aria-valuemin="0" '
            f'aria-valuemax="{target}" aria-valuenow="{value}"><div class="meter-fill" style="width:{pct:.1f}%">'
            f'</div></div></div>')


def _hero(vm: dict, now: datetime) -> str:
    verdict = VERDICT.get(vm["verdict"], vm["verdict"])
    if vm["final"]:
        note = "Soglie raggiunte: questo è l'esito dell'analisi finale preregistrata."
    else:
        note = "Esito provvisorio: l'analisi finale arriva con le soglie preregistrate."
    if vm["last_cycle"] is None:
        status = '<p class="alert">Nessun ciclo nell\'archivio.</p>'
    else:
        age = now - datetime.fromisoformat(vm["last_cycle"])
        if age > STALE_AFTER:
            status = (f'<p class="alert">Attenzione: nessun ciclo da {age.total_seconds() / 3600:.1f} ore '
                      f'(ultimo: {_t(vm["last_cycle"])} UTC). Il demone è fermo?</p>')
        else:
            status = f'<p class="muted small">Ultima candela elaborata: {_t(vm["last_cycle"])} UTC.</p>'
    p = vm["progress"]
    return (f"<header><h1>{escape(verdict)}</h1>"
            f'<p class="muted">Gli analisti LLM ({PRIMARY}) battono la sola analisi '
            f"tecnica? {note}</p>{status}"
            f'{_meter("Candidati risolti", p["n"], p["n_target"])}'
            f'{_meter("Giorni con dati", p["days"], p["days_target"])}</header>')


def _signals(vm: dict) -> str:
    if not vm["signals"]:
        return "<section><h2>Ultimi segnali</h2><p class=\"muted\">Nessun segnale: compaiono al primo candidato.</p></section>"
    rows = []
    for s in vm["signals"]:
        if s["decision"] == "TRADE":
            d = _digits(s["symbol"])
            reason = (f"ingresso {s['entry']:.{d}f}, stop {s['sl']:.{d}f}, target {s['tp']:.{d}f}, "
                      f"{s['lot'] or 0:.2f} lotti")
        else:
            reason = HOLD.get(s["hold_reason"], s["hold_reason"] or "")
        outcome = s["outcome"] or ("aperto" if s["decision"] == "TRADE" else "—")
        rows.append(f"<tr><td><strong>{escape(s['symbol'])}</strong> {escape(s['direction'])}"
                    f'<div class="muted mono">{_t(s["time"])}</div></td>'
                    f'<td class="num nowrap">{s["p"]:.2f} / {s["p_star"]:.2f}</td>'
                    f"<td>{escape(s['decision'])}" + (f'<div class="muted">{escape(reason)}</div>' if reason else "")
                    + f"</td><td>{escape(outcome)}</td></tr>")
    return ("<section><h2>Ultimi segnali</h2>"
            '<p class="muted small">p è la probabilità stimata di TP, p* quella di pareggio dopo i costi; '
            "l'esito è quello virtuale, anche per i HOLD. Orari UTC. Per copiare un TRADE a mano: i livelli valgono "
            "alla chiusura della candela e il lotto è calcolato sul capitale simulato, non sul saldo del tuo conto.</p>"
            '<div class="scroll"><table><thead><tr><th>Candela</th><th class="num">p / p*</th><th>Decisione</th>'
            "<th>Esito</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>")


def _positions(vm: dict) -> str:
    if not vm["positions"]:
        body = '<p class="muted">Nessuna posizione aperta nel broker simulato.</p>'
    else:
        rows = "".join(f"<tr><td>{escape(p['symbol'])}</td><td>{escape(p['direction'])}</td>"
                       f'<td class="num">{p["lots"]:.2f}</td><td class="num">{p["entry"]:.{_digits(p["symbol"])}f}</td>'
                       f'<td class="num">{p["sl"]:.{_digits(p["symbol"])}f}</td>'
                       f'<td class="num">{p["tp"]:.{_digits(p["symbol"])}f}</td></tr>'
                       for p in vm["positions"])
        exposure = ", ".join(f"{escape(c)} {'+' if v > 0 else '−'}{abs(v)}" for c, v in sorted(vm["exposure"].items()))
        body = ('<div class="scroll"><table><thead><tr><th>Simbolo</th><th>Direzione</th><th class="num">Lotti</th>'
                '<th class="num">Ingresso</th><th class="num">Stop</th><th class="num">Target</th></tr></thead>'
                f"<tbody>{rows}</tbody></table></div>"
                f'<p class="small" style="margin-top:12px">Esposizione per valuta: {exposure or "nessuna"}.</p>')
    return f"<section><h2>Posizioni simulate aperte</h2>{body}</section>"


W, H, PAD_L, PAD_R, PAD_T, PAD_B = 360, 200, 36, 96, 12, 28  # disegnati per lo schermo del telefono


def _curve(vm: dict) -> str:
    curve = vm["curve"]
    if not curve:
        return ("<section><h2>Risultato cumulato in R</h2><p class=\"muted\">Nessun trade risolto: la curva compare "
                "al primo TRADE con esito.</p></section>")
    values = [0.0] + [c["net"] for c in curve] + [c["gross"] for c in curve]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(curve)

    def x(i: int) -> float:
        return PAD_L + (W - PAD_L - PAD_R) * (i / n)

    def y(v: float) -> float:
        return PAD_T + (H - PAD_T - PAD_B) * (1 - (v - lo) / span)

    def path(key: str) -> str:
        return "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate([0.0] + [c[key] for c in curve]))

    dots = []
    for i, c in enumerate(curve, start=1):
        tip = f"Trade {i}, {_t(c['time'])}: netto {_signed(c['net'])} R, lordo {_signed(c['gross'])} R"
        dots.append(f'<g><title>{escape(tip)}</title><circle class="hit" cx="{x(i):.1f}" cy="{y(c["net"]):.1f}" r="12"/>'
                    f'<circle class="dot-gross" cx="{x(i):.1f}" cy="{y(c["gross"]):.1f}" r="4"/>'
                    f'<circle class="dot-net" cx="{x(i):.1f}" cy="{y(c["net"]):.1f}" r="4"/></g>')
    last = curve[-1]
    label_net, label_gross = y(last["net"]), y(last["gross"])
    if abs(label_net - label_gross) < 14:  # etichette dirette senza sovrapporsi
        label_gross = label_net + (14 if last["gross"] < last["net"] else -14)
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="R cumulato netto e lordo dei trade risolti">'
           f'<line class="axis" x1="{PAD_L}" x2="{W - PAD_R}" y1="{H - PAD_B}" y2="{H - PAD_B}"/>'
           f'<line class="zero" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>'
           f'<text x="{PAD_L - 6}" y="{y(0) + 4:.1f}" text-anchor="end">0</text>'
           + "".join(f'<text x="{PAD_L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{_signed(v)}</text>'
                     for v in (hi, lo) if abs(v) > 1e-9)  # lo zero ha già la sua etichetta
           + f'<path class="gross" d="{path("gross")}"/><path class="net" d="{path("net")}"/>{"".join(dots)}'
           f'<text class="label" x="{x(n) + 10:.1f}" y="{label_net + 4:.1f}">netto {_signed(last["net"])} R</text>'
           f'<text class="label" x="{x(n) + 10:.1f}" y="{label_gross + 4:.1f}">lordo {_signed(last["gross"])} R</text>'
           f'<text x="{(PAD_L + W - PAD_R) / 2:.1f}" y="{H - 6}" text-anchor="middle">trade risolti, in ordine</text>'
           "</svg>")
    return (f"<section><h2>Risultato cumulato in R</h2>"
            f'<p class="muted small">TRADE risolti della variante di produzione ({n}). La distanza tra le due linee è '
            f"il costo.</p>"
            '<div class="legend"><span><span class="swatch"></span>netto</span>'
            '<span><span class="swatch gross"></span>lordo</span></div>'
            f"{svg}</section>")


def _variants(vm: dict) -> str:
    shown = [v for v in vm["variants"] if v["available"]]
    missing = [v["name"] for v in vm["variants"] if not v["available"]]
    rows = "".join(
        f"<tr><td>{escape(v['name'])}</td><td class=\"num\">{v['n']}</td>"
        f"<td class=\"num\">{_signed(v['bss']) if v['bss'] is not None else '—'}</td>"
        f"<td class=\"num\">{v['trades']}</td>"
        f"<td class=\"num\">{_signed(v['mean_r_net_trade']) if v['mean_r_net_trade'] is not None else '—'}</td></tr>"
        for v in shown)
    plot = ""
    scored = [v for v in shown if v["bss"] is not None]
    if scored:
        lim = 1.25 * max(0.05, max(abs(v["bss"]) for v in scored))  # margine: i punti non toccano il bordo
        row_h, left, right = 24, 104, 344
        height = row_h * len(scored) + 24
        cx = (left + right) / 2

        def x(b: float) -> float:
            return cx + (right - cx) * b / lim

        marks = "".join(
            f'<g><title>{escape(v["name"])}: BSS {_signed(v["bss"])}</title>'
            f'<text x="{left - 10}" y="{14 + i * row_h + 4}" text-anchor="end">{escape(v["name"])}</text>'
            f'<line class="axis" x1="{left}" x2="{right}" y1="{14 + i * row_h}" y2="{14 + i * row_h}"/>'
            f'<circle class="dot" cx="{x(v["bss"]):.1f}" cy="{14 + i * row_h}" r="5"/></g>'
            for i, v in enumerate(scored))
        plot = (f'<svg viewBox="0 0 360 {height}" role="img" aria-label="Brier skill score rispetto a p0 per variante">'
                f'<line class="zero" x1="{cx}" x2="{cx}" y1="4" y2="{height - 18}"/>{marks}'
                f'<text x="{cx}" y="{height - 4}" text-anchor="middle">0 = come p0</text>'
                f'<text x="{right}" y="{height - 4}" text-anchor="end">{_signed(lim)}</text>'
                f'<text x="{left}" y="{height - 4}">{_signed(-lim)}</text></svg>')
    note = (f'<p class="muted small">Non disponibili: {escape(", ".join(missing))}.</p>' if missing else "")
    return ("<section><h2>Varianti a confronto</h2>"
            '<p class="muted small">Brier skill score rispetto a p0: sopra zero la variante stima meglio della sola '
            "geometria di stop e target.</p>" + plot +
            '<div class="scroll"><table><thead><tr><th>Variante</th><th class="num">Esiti</th><th class="num">BSS</th>'
            '<th class="num">TRADE</th><th class="num">R netto medio</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>{note}</section>")


def _calibration(vm: dict) -> str:
    bins = vm["calibration"]
    if not bins:
        return ""
    size, pad = 260, 30

    def s(v: float) -> float:
        return pad + (size - 2 * pad) * v

    dots = "".join(f'<g><title>p media {b["p_mean"]:.2f}, TP osservati {b["y_rate"]:.2f}, n {b["n"]}</title>'
                   f'<circle class="dot" cx="{s(b["p_mean"]):.1f}" cy="{s(1 - b["y_rate"]):.1f}" r="5"/></g>'
                   for b in bins)
    svg = (f'<svg viewBox="0 0 {size} {size}" style="max-width:320px" role="img" aria-label="Calibrazione">'
           f'<line class="axis" x1="{s(0)}" x2="{s(1)}" y1="{s(1)}" y2="{s(0)}"/>'
           f'<line class="axis" x1="{s(0)}" x2="{s(1)}" y1="{s(1)}" y2="{s(1)}"/>'
           f'<line class="axis" x1="{s(0)}" x2="{s(0)}" y1="{s(0)}" y2="{s(1)}"/>{dots}'
           f'<text x="{s(0.5)}" y="{size - 6}" text-anchor="middle">p stimata</text>'
           f'<text x="10" y="{s(0.5)}" transform="rotate(-90 10 {s(0.5)})" text-anchor="middle">TP osservati</text>'
           "</svg>")
    return ("<section><h2>Calibrazione</h2>"
            f'<p class="muted small">Gruppi di pari numerosità di {escape(vm["production_variant"])}: sulla diagonale '
            f"la probabilità stimata coincide con la frequenza osservata.</p>{svg}</section>")


def _coverage(vm: dict) -> str:
    c = vm["coverage"]
    return ("<section><h2>Copertura</h2><dl>"
            f"<div><dt>Cicli completati</dt><dd>{c['cycles_done']}</dd></div>"
            f"<div><dt>Cicli in errore</dt><dd>{c['cycles_error']}</dd></div>"
            f"<div><dt>Candidati con esito</dt><dd>{c['resolved']}</dd></div>"
            f"<div><dt>In attesa di esito</dt><dd>{c['pending']}</dd></div></dl></section>")


def render(vm: dict, generated_at: datetime) -> str:
    return TEMPLATE.substitute(
        hero=_hero(vm, generated_at), signals=_signals(vm), positions=_positions(vm), curve=_curve(vm),
        variants=_variants(vm), calibration=_calibration(vm), coverage=_coverage(vm),
        generated=generated_at.strftime("%d/%m/%Y %H:%M"))


def write_dashboard(db: str | Path, out: str | Path, production_variant: str, now: datetime) -> None:
    """Rigenera la pagina dall'archivio (sola lettura) con scrittura atomica: file temporaneo nella stessa
    cartella e os.replace, così chi la apre (anche da una cartella sincronizzata) non vede mai metà pagina."""
    html = render(viewmodel(load_archive(Path(db)), production_variant=production_variant), generated_at=now)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, target)
