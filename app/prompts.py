"""Prompt separati per gli analisti (D-004). Il tecnico vede solo prezzi, indicatori e trend H1;
il macro solo le notizie visibili alla chiusura. Nessuno vede il candidato, il conto o il rischio:
la direzione dell'analista deve essere indipendente, il confronto col candidato lo fa extractors.py.
La versione di ogni prompt è l'hash del suo template e finisce in archivio con ogni chiamata."""
import hashlib

import pandas as pd

from domain.news import NewsItem
from domain.pip import pip_size

_SCHEMA = """Rispondi SOLO con un oggetto JSON con esattamente questi campi:
{{"direzione": -1 | 0 | 1, "forza": 0..3, "orizzonte": "intraday" | "giorni", "motivazioni": [al massimo 3 frasi brevi]}}
direzione: 1 = la coppia salirà, -1 = scenderà, 0 = nessuna indicazione. forza: 0 = nulla, 3 = netta.
Nessun altro campo, nessun testo fuori dal JSON."""

TECHNICAL_SYSTEM = "Sei un analista tecnico del mercato forex. Valuti solo i dati di prezzo forniti.\n" + _SCHEMA
TECHNICAL_USER = """Coppia: {symbol}, timeframe M15. Trend H1 (chiusura vs EMA50): {htf_trend}.
Ultime candele chiuse (ora UTC, apertura, massimo, minimo, chiusura):
{candles}
Indicatori sull'ultima candela: RSI14 {rsi:.1f}, EMA20 {ema:.{d}f}, MACD istogramma {macd_hist:.{dh}f}, ATR14 {atr:.{d}f},
Bollinger {bb_lower:.{d}f} / {bb_mid:.{d}f} / {bb_upper:.{d}f}."""

MACRO_SYSTEM = ("Sei un analista macroeconomico del mercato forex. Valuti solo le notizie fornite, "
                "senza dati di prezzo.\n" + _SCHEMA +
                "\nOgni motivazione è UNA sola frase di al massimo 30 parole (meno di 200 caratteri): "
                "cita il fatto decisivo, non riassumere tutte le notizie.")
MACRO_USER = """Coppia: {symbol}. Notizie disponibili (pubblicazione UTC, fonte, titolo):
{news}"""


def prompt_version(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()[:10]


TECHNICAL_PROMPT_VERSION = "tecnico-" + prompt_version(TECHNICAL_SYSTEM + TECHNICAL_USER)
MACRO_PROMPT_VERSION = "macro-" + prompt_version(MACRO_SYSTEM + MACRO_USER)


def build_technical_prompt(symbol: str, bars: pd.DataFrame, htf_trend: str, last_n: int = 20) -> tuple[str, str]:
    """bars: candele chiuse con le colonne di app.features.add_indicators."""
    d = 3 if pip_size(symbol) == 0.01 else 5
    tail = bars.tail(last_n)
    candles = "\n".join(f"{r.timestamp:%H:%M} {r.open:.{d}f} {r.high:.{d}f} {r.low:.{d}f} {r.close:.{d}f}"
                        for r in tail.itertuples())
    last = tail.iloc[-1]
    user = TECHNICAL_USER.format(symbol=symbol, htf_trend=htf_trend, candles=candles, d=d, dh=d + 1,
                                 rsi=last["rsi"], ema=last["ema_20"], macd_hist=last["macd_hist"], atr=last["atr"],
                                 bb_lower=last["bb_lower"], bb_mid=last["bb_mid"], bb_upper=last["bb_upper"])
    return TECHNICAL_SYSTEM.format(), user


def build_macro_prompt(symbol: str, news: list[NewsItem]) -> tuple[str, str]:
    """news: già filtrate con domain.news.visible_news."""
    lines = "\n".join(f"- {n.published_at:%Y-%m-%d %H:%M} | {n.source} | {n.headline}" for n in news)
    return MACRO_SYSTEM.format(), MACRO_USER.format(symbol=symbol, news=lines or "Nessuna notizia disponibile.")
