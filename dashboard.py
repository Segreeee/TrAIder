"""
Dashboard (Streamlit) in SOLA LETTURA (P3.30) fino alla dashboard nuova sull'archivio SQLite (P6.03).

Mostra lo storico dei segnali della vecchia dashboard (logs/signals_history.json, mai modificato qui)
e le sue statistiche. Non chiama LLM, MT5 o broker: i segnali li genera il demone (main.py) e gli esiti
li risolve app/resolve.py. Attenzione: gli orari dello storico legacy sono sfasati di 2 ore (T-007).

Avvio: streamlit run dashboard.py
"""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from app.config import Settings

HISTORY_FILE = Path("logs/signals_history.json")

# --- Palette (validated reference instance, light surface) ---------------- #
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
SURFACE = "#fcfcfb"
GRIDLINE = "#e1e0d9"

st.set_page_config(page_title="TrAIder — AI Trading Agent", page_icon="📈", layout="wide")


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


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
    cfg = Settings()

    t1, t2, t3, t4 = st.columns(4)
    render_stat_tile(t1, "Asset monitorati", str(len(cfg.symbols)))
    render_stat_tile(t2, "Timeframe", cfg.timeframe)
    render_stat_tile(t3, "Capitale", f"{cfg.account_balance:,.0f} EUR")
    render_stat_tile(t4, "Rischio/trade", f"{cfg.risk_per_trade_pct:.1f}%")
    st.write("")

    st.info(
        "Dashboard in sola lettura: mostra lo storico della vecchia dashboard. I segnali nuovi li genera "
        "il demone (python main.py) e finiscono nell'archivio SQLite; la loro dashboard arriva in P6.03.",
        icon="ℹ️",
    )

    history = load_history()
    if not history:
        st.write("Nessuno storico legacy da mostrare.")
        return

    st.subheader("Storico segnali della vecchia dashboard")
    live_stats = summarize_live_outcomes(history)
    l1, l2, l3, l4 = st.columns(4)
    render_stat_tile(l1, "Trade risolti", str(live_stats["resolved"]))
    render_stat_tile(l2, "Win rate reale", f"{live_stats['win_rate_pct']}%")
    render_stat_tile(l3, "R totale realizzato", str(live_stats["total_r"]))
    render_stat_tile(l4, "Ancora aperti", str(live_stats["pending"]))
    st.caption(
        "Calcolato sui soli segnali BUY/SELL storici: 'risolti' = TP o SL gia' toccato "
        "(o orizzonte di 24h scaduto), 'aperti' = mai verificati. Orari sfasati di 2 ore (T-007)."
    )

    hist_df = pd.DataFrame(history[::-1])
    # Voci storiche precedenti all'introduzione del campo "symbol" possono mancarlo.
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

    st.dataframe(filtered_df, width="stretch", hide_index=True)
    st.download_button(
        "⬇️ Esporta storico filtrato (CSV)",
        data=filtered_df.to_csv(index=False).encode("utf-8"),
        file_name=f"traider_storico_{datetime.now():%Y%m%d_%H%M%S}.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
