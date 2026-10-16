"""
Calcolo oggettivo della confidenza di un segnale.

Sostituisce il `confidence_percentage` autodichiarato dall'LLM (che, come
osservato empiricamente, converge spesso su valori "tondi" ripetuti invece di
riflettere una vera calibrazione) con una formula basata su tre componenti
misurabili indipendentemente dal modello:

1. Accordo nell'ensemble: quante delle personas indipendenti (tecnico, macro)
   concordano con l'azione finale scelta dal manager.
2. Confluenza tecnica: quanti indicatori indipendenti (prezzo vs EMA20, MACD,
   RSI, prezzo vs Bollinger mid, trend timeframe superiore) puntano nella
   stessa direzione dell'azione finale.
3. Qualita' rischio/rendimento: il rapporto reward/risk reale del trade,
   normalizzato (un R:R piu' alto e' un setup piu' solido).

Nessuna di queste tre componenti viene "detta" dal modello: sono tutte
ricalcolate da dati strutturati (indicatori, prezzi, azioni dichiarate).
"""
from typing import Optional

from core.risk_manager import compute_risk_reward_ratio

# Pesi della formula (sommano a 1.0) — accordo e confluenza pesano il doppio
# della qualita' R:R perche' misurano la direzione del segnale, non solo la
# sua convenienza in caso di successo.
WEIGHT_AGREEMENT = 0.4
WEIGHT_CONFLUENCE = 0.4
WEIGHT_RR = 0.2
RR_NORMALIZATION_CAP = 3.0  # un R:R >= 3 vale il punteggio pieno sulla componente R:R


def ensemble_agreement(persona_actions: list[str], final_action: str) -> float:
    """Frazione (0-1) delle personas che concordano con l'azione finale scelta dal manager."""
    if not persona_actions:
        return 0.5  # nessun ensemble disponibile: componente neutra, non penalizzante ne' premiante
    agreeing = sum(1 for a in persona_actions if a == final_action)
    return agreeing / len(persona_actions)


def technical_confluence(action: str, indicators: dict, htf_trend: Optional[dict]) -> float:
    """
    Frazione (0-1) di indicatori tecnici indipendenti allineati con `action`.
    Ogni indicatore vota rialzista/ribassista/neutro (astensione); la
    confluenza e' calcolata solo sui voti non neutri.
    """
    bullish_votes = 0
    bearish_votes = 0

    last_close = indicators.get("last_close")
    ema_20 = indicators.get("ema_20")
    if last_close is not None and ema_20 is not None and last_close != ema_20:
        bullish_votes += last_close > ema_20
        bearish_votes += last_close < ema_20

    macd_hist = indicators.get("macd_hist")
    if macd_hist is not None and macd_hist != 0:
        bullish_votes += macd_hist > 0
        bearish_votes += macd_hist < 0

    rsi = indicators.get("rsi_14")
    if rsi is not None and rsi != 50:
        bullish_votes += rsi > 50
        bearish_votes += rsi < 50

    bb_mid = indicators.get("bb_mid")
    if last_close is not None and bb_mid is not None and last_close != bb_mid:
        bullish_votes += last_close > bb_mid
        bearish_votes += last_close < bb_mid

    if htf_trend and htf_trend.get("trend") in ("rialzista", "ribassista"):
        bullish_votes += htf_trend["trend"] == "rialzista"
        bearish_votes += htf_trend["trend"] == "ribassista"

    total_votes = bullish_votes + bearish_votes
    if total_votes == 0:
        return 0.5  # nessun indicatore disponibile: componente neutra

    aligned_votes = bullish_votes if action == "BUY" else bearish_votes
    return aligned_votes / total_votes


def confidence_breakdown(
    final_action: str,
    persona_actions: list[str],
    indicators: dict,
    htf_trend: Optional[dict],
    entry_price: float,
    take_profit_price: float,
    stop_loss_price: float,
) -> dict:
    """Componenti della formula (per trasparenza in UI) + punteggio finale 0-100."""
    if final_action not in ("BUY", "SELL"):
        return {
            "agreement_pct": None, "confluence_pct": None,
            "rr_ratio": None, "rr_score_pct": None, "score_pct": 0,
        }

    agreement = ensemble_agreement(persona_actions, final_action)
    confluence = technical_confluence(final_action, indicators, htf_trend)
    rr_ratio = compute_risk_reward_ratio(entry_price, take_profit_price, stop_loss_price)
    rr_score = min(rr_ratio / RR_NORMALIZATION_CAP, 1.0)

    weighted = WEIGHT_AGREEMENT * agreement + WEIGHT_CONFLUENCE * confluence + WEIGHT_RR * rr_score

    return {
        "agreement_pct": round(agreement * 100),
        "confluence_pct": round(confluence * 100),
        "rr_ratio": round(rr_ratio, 2),
        "rr_score_pct": round(rr_score * 100),
        "score_pct": round(weighted * 100),
    }


def compute_confidence(
    final_action: str,
    persona_actions: list[str],
    indicators: dict,
    htf_trend: Optional[dict],
    entry_price: float,
    take_profit_price: float,
    stop_loss_price: float,
) -> int:
    """Punteggio finale 0-100 della formula — vedi `confidence_breakdown` per i dettagli usati in UI."""
    return confidence_breakdown(
        final_action, persona_actions, indicators, htf_trend,
        entry_price, take_profit_price, stop_loss_price,
    )["score_pct"]
