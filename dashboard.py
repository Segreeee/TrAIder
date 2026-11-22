"""
Dashboard grafica (Streamlit) - interfaccia advisory per l'AI Trading Agent.

Analizza tutti gli asset in `settings.symbols` (un ciclo dati->news->prompt->
Qwen->risk_manager per ciascuno) e mette in evidenza quello con la confidenza
più alta tra i segnali attuabili (BUY/SELL). Non esegue mai ordini in
autonomia: mostra solo i segnali, gia' validati/ricalcolati dal RiskManager,
cosi' che l'utente possa valutarli ed eseguirli manualmente (anche su conto
reale) se lo ritiene opportuno.

Avvio: streamlit run dashboard.py
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config.settings import settings
from core.backtester import realized_result, simulate_outcome
from core.confidence import confidence_breakdown
from core.data_feed import DataFeedError, MarketDataFeed
from core.news_feed import NewsFeed, build_news_feed
from core.ensemble import active_analysts, build_analysts, build_judge, collect_persona_signals, judge_signal
from core.prompt_builder import build_user_prompt
from core.qwen_brain import QwenBrain, QwenBrainError
from core.risk_manager import (
    MIN_RISK_REWARD_RATIO,
    RiskManager,
    compute_risk_reward_ratio,
    meets_min_risk_reward,
    pip_size_for_symbol,
)

HISTORY_FILE = Path("logs/signals_history.json")
MAX_RESOLUTION_CANDLES = 96  # stesso orizzonte del backtester (24h su M15): oltre, si chiude come TIMEOUT

# --- Palette (validated reference instance, light surface) ---------------- #
# Status roles are fixed/never themed; categorical slots keep the documented
# adjacency order. Every color below carries an icon+label alongside it, so
# identity never rests on hue alone (required for the sub-3:1 light-surface
# roles, e.g. "serious").
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

STATUS_GOOD = "#0ca30c"      # BUY / bullish
STATUS_CRITICAL = "#d03b3b"  # SELL / bearish
STATUS_SERIOUS = "#ec835a"   # ERROR
STATUS_NEUTRAL = INK_MUTED   # HOLD

CATEGORICAL_BLUE = "#2a78d6"    # EMA 20
CATEGORICAL_ORANGE = "#eb6834"  # RSI 14

ACTION_COLOR = {"BUY": STATUS_GOOD, "SELL": STATUS_CRITICAL, "HOLD": STATUS_NEUTRAL, "ERROR": STATUS_SERIOUS}
ACTION_ICON = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪", "ERROR": "⚠️"}
ACTION_LABEL = {k: f"{ACTION_ICON[k]} {k}" for k in ACTION_COLOR}
ACTION_LABEL["ERROR"] = "⚠️ ERRORE"

st.set_page_config(page_title="TrAIder — AI Trading Agent", page_icon="📈", layout="wide")


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_history(history: list) -> None:
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history[-200:], indent=2), encoding="utf-8")


def prepare_symbol_context(feed: MarketDataFeed, news_feed: NewsFeed, symbol: str) -> dict:
    """Recupera dati/indicatori/notizie e costruisce il prompt base per un simbolo — nessuna chiamata LLM."""
    raw_df = feed.fetch_ohlcv(symbol=symbol)
    enriched_df = feed.add_indicators(raw_df)
    market_payload = feed.to_compact_payload(enriched_df)
    htf_trend = feed.get_higher_timeframe_trend(symbol=symbol)
    news_items = news_feed.get_latest_news(symbol)

    base_prompt = build_user_prompt(
        symbol=symbol, timeframe=settings.timeframe, market_payload=market_payload,
        news_items=news_items, account_balance=settings.account_balance,
        risk_per_trade_pct=settings.risk_per_trade_pct, htf_trend=htf_trend,
    )

    return {
        "symbol": symbol, "enriched_df": enriched_df, "market_payload": market_payload,
        "htf_trend": htf_trend, "news_items": news_items, "base_prompt": base_prompt,
    }


def apply_risk_gate(signal: dict, entry_price: float, symbol: str) -> None:
    """
    Ricalcola indipendentemente il R:R e il lot_size (mai fidandosi del solo
    self-report del modello) e muta `signal` in place. Condiviso da tutte le
    modalita' di analisi (screening, due-fasi, ensemble).
    """
    if signal["action"] not in ("BUY", "SELL"):
        return
    if not meets_min_risk_reward(entry_price, signal["take_profit_price"], signal["stop_loss_price"], action=signal["action"]):
        actual_rr = compute_risk_reward_ratio(entry_price, signal["take_profit_price"], signal["stop_loss_price"])
        signal["action"] = "HOLD"
        signal["lot_size"] = 0.0
        signal["reasoning"] += (
            f" [Segnale declassato a HOLD dal risk manager: R:R reale {actual_rr:.2f} "
            f"sotto la soglia minima {MIN_RISK_REWARD_RATIO}.]"
        )
    else:
        risk_manager = RiskManager(settings.account_balance, settings.risk_per_trade_pct)
        signal["lot_size"] = risk_manager.cap_llm_lot_size(
            llm_lot_size=signal["lot_size"], entry_price=entry_price,
            stop_loss_price=signal["stop_loss_price"], pip_size=pip_size_for_symbol(symbol),
        )


def decide(ctx: dict, brain: QwenBrain, two_phase: bool) -> dict:
    """
    Dato un contesto gia' preparato, esegue 1 chiamata LLM (solo verdetto) o 2
    (analisi libera + verdetto) e applica il risk gate. two_phase=False e' la
    modalita' economica di screening.
    """
    if two_phase:
        analysis = brain.run_reasoning_pass(ctx["base_prompt"])
        decision_prompt = build_user_prompt(
            symbol=ctx["symbol"], timeframe=settings.timeframe, market_payload=ctx["market_payload"],
            news_items=ctx["news_items"], account_balance=settings.account_balance,
            risk_per_trade_pct=settings.risk_per_trade_pct, htf_trend=ctx["htf_trend"],
            preliminary_analysis=analysis,
        )
    else:
        analysis = None
        decision_prompt = ctx["base_prompt"]

    signal = brain.get_trade_signal(decision_prompt)
    entry_price = ctx["market_payload"]["indicators"]["last_close"]
    apply_risk_gate(signal, entry_price, ctx["symbol"])

    return {
        "symbol": ctx["symbol"],
        "enriched_df": ctx["enriched_df"],
        "market_payload": ctx["market_payload"],
        "htf_trend": ctx["htf_trend"],
        "news_items": ctx["news_items"],
        "analysis": analysis,
        "two_phase": two_phase,
        "ensemble": None,
        "signal": signal,
        "error": None,
    }


def decide_ensemble(ctx: dict, brain: QwenBrain, analysts: dict) -> dict:
    """
    Deep-dive "ensemble" (LLM-as-a-judge): due analisti locali (Ollama: tecnico,
    macro/news) emettono un verdetto indipendente sullo stesso asset; il giudice
    (`brain`, terzo modello locale) arbitra e decide. Se nessun analista risponde,
    ricade sul flusso a due fasi single-model.

    La confidenza NON e' presa dal self-report del modello: viene ricalcolata
    con `confidence_breakdown` (accordo tra gli analisti + confluenza tecnica
    indipendente + qualita' R:R) — vedi core/confidence.py.
    """
    analysts = active_analysts(analysts, has_news=bool(ctx["news_items"]))
    persona_signals = collect_persona_signals(ctx["base_prompt"], analysts)
    if not persona_signals:
        return decide(ctx, brain, two_phase=True)

    signal = judge_signal(
        brain, persona_signals, symbol=ctx["symbol"], market_payload=ctx["market_payload"],
        news_items=ctx["news_items"], htf_trend=ctx["htf_trend"],
        expected_analysts=len(analysts),
    )

    entry_price = ctx["market_payload"]["indicators"]["last_close"]
    apply_risk_gate(signal, entry_price, ctx["symbol"])

    breakdown = confidence_breakdown(
        final_action=signal["action"],
        persona_actions=[sig["action"] for sig in persona_signals.values()],
        indicators=ctx["market_payload"]["indicators"],
        htf_trend=ctx["htf_trend"],
        entry_price=entry_price,
        take_profit_price=signal.get("take_profit_price", entry_price),
        stop_loss_price=signal.get("stop_loss_price", entry_price),
    )
    signal["confidence_percentage"] = breakdown["score_pct"]

    return {
        "symbol": ctx["symbol"],
        "enriched_df": ctx["enriched_df"],
        "market_payload": ctx["market_payload"],
        "htf_trend": ctx["htf_trend"],
        "news_items": ctx["news_items"],
        "analysis": None,
        "two_phase": True,
        "ensemble": persona_signals,
        "confidence_breakdown": breakdown,
        "signal": signal,
        "error": None,
    }


def run_multi_asset_analysis(progress_callback=None, deep_dive_top_n: int = 2) -> list:
    """
    Analizza tutti i simboli in settings.symbols in due stadi, per limitare le
    chiamate LLM (costo/tempo) senza rinunciare al ragionamento approfondito
    dove conta di piu':

    1. Screening: 1 sola chiamata (verdetto diretto, senza fase di ragionamento
       libero) per ogni asset.
    2. Deep-dive: solo i migliori `deep_dive_top_n` candidati attuabili (BUY/SELL,
       per confidenza e poi R:R) vengono ri-analizzati con la pipeline completa
       a due fasi. Gli altri mantengono il verdetto di screening.

    Con N asset e top_n candidati: N + 3*top_n chiamate — screening a 1 sola
    chiamata per tutti, ensemble (2 analisti + giudice, locali) solo dove conta di piu'.
    """
    feed = MarketDataFeed()
    feed.connect()
    brain = build_judge()
    analysts = build_analysts()
    # La dashboard non invia ordini: le notizie mock sono ammesse, ma il default resta "none".
    news_feed = build_news_feed(settings.news_provider, dry_run=True)

    total_steps = len(settings.symbols) + deep_dive_top_n
    step = 0

    def tick(label: str) -> None:
        nonlocal step
        if progress_callback:
            progress_callback(step, total_steps, label)
        step += 1

    screened: list[dict] = []
    try:
        for symbol in settings.symbols:
            tick(f"Screening {symbol}...")
            try:
                ctx = prepare_symbol_context(feed, news_feed, symbol)
                screened.append(decide(ctx, brain, two_phase=False))
            except (DataFeedError, QwenBrainError) as e:
                screened.append({
                    "symbol": symbol, "enriched_df": None, "market_payload": None,
                    "htf_trend": None, "news_items": [], "analysis": None,
                    "two_phase": None, "ensemble": None, "signal": None, "error": str(e),
                })

        actionable = [r for r in screened if not r["error"] and r["signal"]["action"] in ("BUY", "SELL")]
        actionable.sort(key=lambda r: (r["signal"]["confidence_percentage"], risk_reward_ratio(r)), reverse=True)
        candidate_symbols = {r["symbol"] for r in actionable[:deep_dive_top_n]}

        final_results = []
        for r in screened:
            if r["symbol"] not in candidate_symbols:
                final_results.append(r)
                continue
            tick(f"Ensemble su {r['symbol']}...")
            try:
                ctx = prepare_symbol_context(feed, news_feed, r["symbol"])
                final_results.append(decide_ensemble(ctx, brain, analysts))
            except (DataFeedError, QwenBrainError) as e:
                final_results.append({**r, "error": str(e)})
    finally:
        feed.shutdown()

    return final_results


def risk_reward_ratio(result: dict) -> float:
    """Rapporto reward/risk (TP vs SL rispetto all'ultimo prezzo) per uno spareggio oggettivo a parita' di confidenza."""
    signal = result["signal"]
    if signal["action"] not in ("BUY", "SELL"):
        return 0.0
    entry = result["market_payload"]["indicators"]["last_close"]
    return compute_risk_reward_ratio(entry, signal["take_profit_price"], signal["stop_loss_price"])


def pick_best(results: list) -> dict | None:
    """
    Sceglie il risultato con confidenza piu' alta tra i segnali attuabili (BUY/SELL).
    A parita' di confidenza (Qwen tende a convergere su pochi valori "tondi"), lo
    spareggio usa il rapporto reward/risk (TP/SL) come criterio oggettivo calcolato
    da noi, non dichiarato dal modello. Fallback sul piu' confidente in assoluto se
    non ci sono segnali attuabili.
    """
    actionable = [r for r in results if r["signal"] and r["signal"]["action"] in ("BUY", "SELL")]
    pool = actionable if actionable else [r for r in results if r["signal"]]
    if not pool:
        return None
    return max(pool, key=lambda r: (r["signal"]["confidence_percentage"], risk_reward_ratio(r)))


def render_candlestick(symbol: str, enriched_df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
        vertical_spacing=0.08, subplot_titles=(f"{symbol} {settings.timeframe}", "RSI(14)"),
    )
    fig.add_trace(
        go.Candlestick(
            x=enriched_df["timestamp"], open=enriched_df["open"], high=enriched_df["high"],
            low=enriched_df["low"], close=enriched_df["close"], name="OHLC",
            increasing=dict(line=dict(color=STATUS_GOOD), fillcolor=STATUS_GOOD),
            decreasing=dict(line=dict(color=STATUS_CRITICAL), fillcolor=STATUS_CRITICAL),
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=enriched_df["timestamp"], y=enriched_df["ema_20"], name="EMA 20",
            line=dict(color=CATEGORICAL_BLUE, width=2),
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=enriched_df["timestamp"], y=enriched_df["rsi"], name="RSI 14",
            line=dict(color=CATEGORICAL_ORANGE, width=2),
        ),
        row=2, col=1,
    )
    # Soglie ipercomprato/ipervenduto: gridline recessiva, non un colore di stato
    # (non sono un segnale a se', solo un riferimento di lettura).
    fig.add_hline(y=70, line_width=1, line_color=BASELINE, row=2, col=1)
    fig.add_hline(y=30, line_width=1, line_color=BASELINE, row=2, col=1)

    fig.update_layout(
        height=500,
        xaxis_rangeslider_visible=False,
        margin=dict(t=40, b=20),
        showlegend=True,
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(color=INK_SECONDARY, family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=GRIDLINE, linecolor=BASELINE, zeroline=False)
    fig.update_yaxes(gridcolor=GRIDLINE, linecolor=BASELINE, zeroline=False)
    fig.update_annotations(font=dict(color=INK_SECONDARY, size=13))
    return fig


def render_signal(symbol: str, signal: dict) -> None:
    color = ACTION_COLOR.get(signal["action"], INK_MUTED)
    icon = ACTION_ICON.get(signal["action"], "•")

    # Identita' di stato = wash di sfondo + bordo pieno; il testo resta in
    # inchiostro primario (mai il colore-dato come colore-testo) e l'icona
    # porta il significato assieme all'etichetta, non il colore da solo.
    st.markdown(
        f"""
        <div style="background-color:{color}14; border:1px solid {color}40; border-left:4px solid {color};
                    padding:14px 20px; border-radius:8px; margin-bottom:16px;
                    display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;">
            <span style="font-size:20px; font-weight:600; color:{INK_PRIMARY};">{symbol}</span>
            <span style="font-size:24px; font-weight:700; color:{INK_PRIMARY};">{icon} {signal['action']}</span>
            <span style="font-size:14px; color:{INK_SECONDARY};">
                Confidenza {signal['confidence_percentage']}%
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if signal["action"] in ("BUY", "SELL"):
        c1, c2, c3 = st.columns(3)
        c1.metric("Lot size (risk-adjusted, max 1% capitale)", f"{signal['lot_size']:.2f}")
        c2.metric("Take Profit", f"{signal['take_profit_price']:.5f}")
        c3.metric("Stop Loss", f"{signal['stop_loss_price']:.5f}")

    st.markdown("**Motivazione del modello:**")
    st.write(signal["reasoning"])


def render_context(r: dict) -> None:
    """Mostra profondita' dell'analisi, trend HTF, ensemble (personas + breakdown confidenza) o analisi preliminare."""
    if r.get("ensemble"):
        st.caption("🧑‍🤝‍🧑 Analisi ensemble (2 analisti + giudice, locali)")
    elif r.get("two_phase"):
        st.caption("🔬 Analisi approfondita (ragionamento a due fasi)")
    elif r.get("two_phase") is False:
        st.caption("⚡ Solo screening rapido (non tra i migliori candidati per l'approfondimento)")

    htf = r.get("htf_trend")
    if htf:
        trend_icon = {"rialzista": "📈", "ribassista": "📉"}.get(htf["trend"], "➡️")
        ema_key = next((k for k in htf if k.startswith("ema_")), None)
        st.caption(
            f"{trend_icon} Trend {htf['timeframe']}: **{htf['trend']}** "
            f"(prezzo {htf['last_close']} vs {ema_key or 'EMA'} {htf.get(ema_key)})"
        )

    if r.get("ensemble"):
        with st.expander("Verdetti indipendenti delle personas + formula di confidenza"):
            for name, sig in r["ensemble"].items():
                st.markdown(f"**{name}** → {ACTION_LABEL.get(sig['action'], sig['action'])}")
                st.caption(sig["reasoning"])
            bd = r.get("confidence_breakdown")
            if bd and bd.get("agreement_pct") is not None:
                st.markdown("**Formula di confidenza (calcolata, non dichiarata dal modello):**")
                st.write(
                    f"Accordo personas: {bd['agreement_pct']}% · Confluenza tecnica: {bd['confluence_pct']}% · "
                    f"R:R {bd['rr_ratio']} (punteggio {bd['rr_score_pct']}%) → **{bd['score_pct']}%**"
                )
            else:
                st.caption("Verdetto finale HOLD: la formula di confidenza si applica solo ai segnali BUY/SELL.")
    elif r.get("analysis"):
        with st.expander("Analisi preliminare del modello (fase di ragionamento)"):
            st.write(r["analysis"])


def render_comparison_table(results: list, best_symbol: str) -> pd.DataFrame:
    rows = []
    for r in results:
        if r["error"]:
            rows.append({
                "Asset": r["symbol"], "Azione": ACTION_LABEL["ERROR"], "Confidenza %": None,
                "R:R": None, "Note": r["error"],
            })
        else:
            s = r["signal"]
            marker = "🏆 " if r["symbol"] == best_symbol else ""
            rr = risk_reward_ratio(r)
            rows.append({
                "Asset": f"{marker}{r['symbol']}",
                "Azione": ACTION_LABEL.get(s["action"], s["action"]),
                "Confidenza %": s["confidence_percentage"],
                "R:R": round(rr, 2) if rr else None,
                "Note": s["reasoning"][:100] + ("…" if len(s["reasoning"]) > 100 else ""),
            })
    df = pd.DataFrame(rows).sort_values(
        ["Confidenza %", "R:R"], ascending=[False, False], na_position="last"
    )
    st.dataframe(df, use_container_width=True, hide_index=True)
    return df


def render_stat_tile(col, label: str, value: str) -> None:
    """Stat tile minimale: label in inchiostro secondario, valore in semibold — niente colore-dato su testo di contesto."""
    col.markdown(
        f"""
        <div style="background-color:{SURFACE}; border:1px solid {GRIDLINE}; border-radius:8px;
                    padding:10px 14px;">
            <div style="font-size:12px; color:{INK_SECONDARY};">{label}</div>
            <div style="font-size:19px; font-weight:600; color:{INK_PRIMARY};">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def resolve_pending_outcomes(feed: MarketDataFeed, history: list) -> int:
    """
    Verifica, per i segnali BUY/SELL passati non ancora risolti, se TP o SL sono
    stati toccati nel frattempo usando dati reali MT5 successivi al momento del
    segnale (stessa logica di simulazione del backtester, applicata in avanti
    ai segnali gia' generati invece che a dati storici sintetici). Aggiorna
    `history` in-place; ritorna quanti segnali sono stati risolti in questa chiamata.
    """
    resolved_count = 0
    now = datetime.now(timezone.utc)

    for entry in history:
        if entry.get("action") not in ("BUY", "SELL"):
            continue
        if entry.get("outcome") not in (None, "PENDING"):
            continue  # gia' risolto definitivamente in precedenza

        symbol = entry.get("symbol")
        tp, sl, entry_price = entry.get("take_profit_price"), entry.get("stop_loss_price"), entry.get("last_close")
        if not symbol or symbol == "N/D" or tp is None or sl is None or entry_price is None:
            continue  # voce storica incompleta (es. precedente all'introduzione di questi campi)

        try:
            signal_time = datetime.fromisoformat(entry["timestamp"])
        except (KeyError, ValueError):
            continue

        try:
            # +1s per escludere la candela stessa del segnale (evita di leggere
            # come "gia' toccato" un movimento avvenuto prima dell'entry).
            future_df = feed.fetch_ohlcv_range(
                symbol=symbol, timeframe=settings.timeframe,
                start=signal_time + timedelta(seconds=1), end=now,
            )
        except DataFeedError:
            continue

        if future_df.empty:
            entry["outcome"] = "PENDING"
            continue

        capped_df = future_df.iloc[:MAX_RESOLUTION_CANDLES]
        outcome, exit_price = simulate_outcome(entry["action"], tp, sl, capped_df)

        if outcome == "TIMEOUT" and len(future_df) < MAX_RESOLUTION_CANDLES:
            entry["outcome"] = "PENDING"  # ancora dentro l'orizzonte di osservazione
            continue

        res = realized_result(entry["action"], entry_price, exit_price, sl,
                              pip_size_for_symbol(symbol), settings.cost_pips)

        entry["outcome"] = outcome
        entry["exit_price"] = exit_price
        entry["pips"] = res["pips"]  # al netto dei costi (COST_PIPS)
        entry["r_multiple"] = res["r_multiple"]  # al netto dei costi
        entry["r_multiple_gross"] = res["r_multiple_gross"]
        entry["resolved_at"] = now.isoformat()
        resolved_count += 1

    if resolved_count:
        save_history(history)
    return resolved_count


def summarize_live_outcomes(history: list) -> dict:
    """Statistiche reali (non backtest) sui segnali BUY/SELL gia' passati per la dashboard, risolti o ancora aperti."""
    actionable = [h for h in history if h.get("action") in ("BUY", "SELL")]
    resolved = [h for h in actionable if h.get("outcome") in ("TP", "SL", "TIMEOUT")]
    wins = [h for h in resolved if h["outcome"] == "TP"]
    pending = [h for h in actionable if h.get("outcome") in (None, "PENDING")]
    r_values = [h["r_multiple"] for h in resolved if h.get("r_multiple") is not None]

    return {
        "resolved": len(resolved),
        "wins": len(wins),
        "pending": len(pending),
        "win_rate_pct": round(len(wins) / len(resolved) * 100, 1) if resolved else 0.0,
        "total_r": round(sum(r_values), 2),
    }


def main() -> None:
    st.title("📈 TrAIder — AI Trading Agent")

    t1, t2, t3, t4 = st.columns(4)
    render_stat_tile(t1, "Asset monitorati", str(len(settings.symbols)))
    render_stat_tile(t2, "Timeframe", settings.timeframe)
    render_stat_tile(t3, "Capitale", f"{settings.account_balance:,.0f} EUR")
    render_stat_tile(t4, "Rischio/trade", f"{settings.risk_per_trade_pct:.1f}%")
    st.write("")

    st.info(
        "Dashboard puramente informativa: analizza tutti gli asset configurati e mette in "
        "evidenza quello con la confidenza piu' alta. Nessun ordine viene mai inviato "
        "automaticamente al conto: l'eventuale esecuzione (anche su conto reale) resta una "
        "tua decisione manuale.",
        icon="ℹ️",
    )

    if "history" not in st.session_state:
        st.session_state.history = load_history()

    deep_dive_top_n = st.slider(
        "Analisi ensemble (2 analisti + giudice, tutti locali Ollama) sui migliori N candidati — gli altri restano allo screening rapido (1 chiamata)",
        min_value=0, max_value=len(settings.symbols), value=min(2, len(settings.symbols)),
    )
    est_calls = len(settings.symbols) + 3 * deep_dive_top_n
    st.caption(
        f"Stima chiamate ai modelli locali Ollama (gratuite): ~{est_calls} "
        f"(1 a testa per lo screening + 2 analisti e 1 giudice per ogni candidato approfondito)."
    )

    if st.button("🔍 Analizza tutti gli asset", type="primary"):
        progress_bar = st.progress(0.0, text="Avvio analisi...")

        def on_progress(i: int, total: int, label: str) -> None:
            progress_bar.progress(min(i / total, 1.0), text=label)

        results = run_multi_asset_analysis(progress_callback=on_progress, deep_dive_top_n=deep_dive_top_n)
        progress_bar.empty()

        st.session_state.last_results = results
        timestamp = datetime.now(timezone.utc).isoformat()
        for r in results:
            if r["error"]:
                continue
            entry = {
                "timestamp": timestamp,
                "symbol": r["symbol"],
                "last_close": r["market_payload"]["indicators"]["last_close"],
                **r["signal"],
            }
            st.session_state.history.append(entry)
        save_history(st.session_state.history)

    if "last_results" in st.session_state:
        results = st.session_state.last_results
        error_results = [r for r in results if r["error"]]
        for r in error_results:
            st.warning(f"**{r['symbol']}**: {r['error']}")

        best = pick_best(results)
        if best is None:
            st.error("Nessun segnale valido ottenuto per nessun asset in questo ciclo.")
        else:
            st.subheader("🏆 Migliore opportunità")
            render_signal(best["symbol"], best["signal"])
            render_context(best)
            st.plotly_chart(
                render_candlestick(best["symbol"], best["enriched_df"]),
                use_container_width=True, key=f"chart_best_{best['symbol']}",
            )

            st.subheader("Confronto tra tutti gli asset analizzati")
            comparison_df = render_comparison_table(results, best["symbol"])
            st.download_button(
                "⬇️ Esporta confronto (CSV)",
                data=comparison_df.to_csv(index=False).encode("utf-8"),
                file_name=f"traider_confronto_{datetime.now():%Y%m%d_%H%M%S}.csv",
                mime="text/csv",
            )

            with st.expander(f"Dettaglio per singolo asset ({len(results)} analizzati)"):
                tabs = st.tabs([r["symbol"] for r in results])
                for tab, r in zip(tabs, results):
                    with tab:
                        if r["error"]:
                            st.error(r["error"])
                            continue
                        render_signal(r["symbol"], r["signal"])
                        render_context(r)
                        st.plotly_chart(
                            render_candlestick(r["symbol"], r["enriched_df"]),
                            use_container_width=True, key=f"chart_tab_{r['symbol']}",
                        )
                        st.markdown("**Notizie considerate:**")
                        for item in r["news_items"]:
                            st.markdown(f"- **{item['headline']}** — *{item['source']}*")
    else:
        st.write("Premi **Analizza tutti gli asset** per generare il primo confronto.")

    if st.session_state.history:
        st.subheader("Storico segnali di questa dashboard")

        if st.button("🔄 Verifica esiti reali dei segnali passati"):
            with st.spinner("Confronto TP/SL con i prezzi reali successivi al segnale..."):
                feed = MarketDataFeed()
                try:
                    feed.connect()
                    n = resolve_pending_outcomes(feed, st.session_state.history)
                except DataFeedError as e:
                    st.error(f"Errore MT5: {e}")
                    n = 0
                finally:
                    feed.shutdown()
            st.success(f"{n} segnali risolti in questo controllo.")

        live_stats = summarize_live_outcomes(st.session_state.history)
        l1, l2, l3, l4 = st.columns(4)
        render_stat_tile(l1, "Trade risolti", str(live_stats["resolved"]))
        render_stat_tile(l2, "Win rate reale", f"{live_stats['win_rate_pct']}%")
        render_stat_tile(l3, "R totale realizzato", str(live_stats["total_r"]))
        render_stat_tile(l4, "Ancora aperti", str(live_stats["pending"]))
        st.caption(
            "Calcolato sui soli segnali BUY/SELL storici: 'risolti' = TP o SL gia' toccato "
            "(o orizzonte di 24h scaduto), 'aperti' = ancora in attesa che il prezzo tocchi uno dei due."
        )

        hist_df = pd.DataFrame(st.session_state.history[::-1])
        # Voci storiche precedenti all'introduzione del campo "symbol" possono
        # mancarlo: normalizzo per evitare che finiscano mescolate a NaN.
        if "symbol" not in hist_df.columns:
            hist_df["symbol"] = "N/D"
        hist_df["symbol"] = hist_df["symbol"].fillna("N/D")

        f1, f2 = st.columns(2)
        asset_filter = f1.multiselect("Filtra per asset", sorted(hist_df["symbol"].astype(str).unique()))
        action_filter = f2.multiselect("Filtra per azione", sorted(hist_df["action"].astype(str).unique()))

        filtered_df = hist_df
        if asset_filter:
            filtered_df = filtered_df[filtered_df["symbol"].isin(asset_filter)]
        if action_filter:
            filtered_df = filtered_df[filtered_df["action"].isin(action_filter)]

        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Esporta storico filtrato (CSV)",
            data=filtered_df.to_csv(index=False).encode("utf-8"),
            file_name=f"traider_storico_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
