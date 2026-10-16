"""
Backtester walk-forward per validare se la pipeline di analisi (indicatori +
due fasi Qwen + risk gate) produce segnali con un edge misurabile su dati
storici reali, invece di restare nel campo delle ipotesi non verificate.

Limiti noti (MVP, dichiarati esplicitamente per non generare falsa fiducia):
- Nessuno storico notizie reale e' disponibile: il prompt di backtest esclude
  le notizie (niente mock "dal futuro" che falserebbe il test).
- Nessun trend multi-timeframe storico allineato punto-per-punto: il campo
  viene omesso in backtest (l'LLM lo vede come "non disponibile").
- Ogni punto campionato costa 1-2 chiamate LLM: il backtest campiona a
  intervalli (`stride`) invece che su ogni candela, per restare sostenibile
  in tempo/costo.
- La simulazione dell'esito e' un semplice walk-forward su TP/SL: non modella
  spread, slippage, commissioni ne' rientri parziali.
"""
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from core.data_feed import MarketDataFeed
from core.prompt_builder import build_user_prompt
from core.qwen_brain import QwenBrain
from core.risk_manager import (
    RiskManager,
    compute_risk_reward_ratio,
    meets_min_risk_reward,
    pip_size_for_symbol,
)

logger = logging.getLogger(__name__)

WARMUP_CANDLES = 60  # candele iniziali scartate per stabilizzare EMA/MACD/BB
MAX_HOLDING_CANDLES = 96  # orizzonte massimo di simulazione forward per trade (96 * M15 = 24h)


@dataclass
class BacktestTrade:
    timestamp: str
    symbol: str
    action: str
    confidence: int
    entry_price: float
    take_profit: Optional[float]
    stop_loss: Optional[float]
    lot_size: Optional[float]
    outcome: str  # "TP", "SL", "TIMEOUT", "HOLD"
    exit_price: Optional[float]
    pips: Optional[float]
    r_multiple: Optional[float]
    reasoning: str


def simulate_outcome(action: str, tp: float, sl: float, future_df: pd.DataFrame) -> tuple[str, Optional[float]]:
    """
    Cammina in avanti tra le candele successive: primo tra TP/SL toccato vince
    (SL se ambigui nella stessa candela). Pubblica perche' riusata sia dal
    backtest storico sia dal tracking live degli esiti reali (dashboard).
    """
    for _, row in future_df.iterrows():
        high, low = row["high"], row["low"]
        if action == "BUY":
            hit_sl, hit_tp = low <= sl, high >= tp
        else:  # SELL
            hit_sl, hit_tp = high >= sl, low <= tp
        if hit_sl:
            return "SL", sl
        if hit_tp:
            return "TP", tp
    if len(future_df) == 0:
        return "TIMEOUT", None
    return "TIMEOUT", float(future_df.iloc[-1]["close"])


def run_backtest(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    account_balance: float,
    risk_per_trade_pct: float,
    stride: int = 8,
    two_phase: bool = False,
    max_signals: Optional[int] = None,
    progress_callback=None,
) -> list[BacktestTrade]:
    """
    Esegue un backtest walk-forward su dati storici reali MT5.

    - stride: ogni quante candele campionare un nuovo punto decisionale
      (es. 8 su M15 = ogni 2 ore).
    - two_phase: se True replica la pipeline live a due passi (analisi libera
      + verdetto); piu' lento e costoso, ma piu' fedele al comportamento reale.
    - max_signals: tetto di sicurezza sul numero di punti valutati.
    """
    feed = MarketDataFeed()
    feed.connect()
    try:
        raw_df = feed.fetch_ohlcv_range(symbol=symbol, timeframe=timeframe, start=start, end=end)
        enriched_df = feed.add_indicators(raw_df)
    finally:
        feed.shutdown()

    if len(enriched_df) <= WARMUP_CANDLES + 1:
        raise ValueError(
            f"Range storico troppo corto ({len(enriched_df)} candele): servono almeno "
            f"{WARMUP_CANDLES + 1} candele per superare il periodo di warm-up degli indicatori."
        )

    brain = QwenBrain()
    risk_manager = RiskManager(account_balance, risk_per_trade_pct)
    pip_size = pip_size_for_symbol(symbol)

    sample_indices = list(range(WARMUP_CANDLES, len(enriched_df) - 1, stride))
    if max_signals:
        sample_indices = sample_indices[:max_signals]

    trades: list[BacktestTrade] = []

    for step, idx in enumerate(sample_indices):
        if progress_callback:
            progress_callback(step, len(sample_indices))

        snapshot_df = enriched_df.iloc[: idx + 1]
        market_payload = MarketDataFeed.to_compact_payload(snapshot_df)
        entry_price = market_payload["indicators"]["last_close"]
        ts = str(snapshot_df.iloc[-1]["timestamp"])

        base_prompt = build_user_prompt(
            symbol=symbol, timeframe=timeframe, market_payload=market_payload,
            news_items=[], account_balance=account_balance, risk_per_trade_pct=risk_per_trade_pct,
        )

        try:
            if two_phase:
                analysis = brain.run_reasoning_pass(base_prompt)
                decision_prompt = build_user_prompt(
                    symbol=symbol, timeframe=timeframe, market_payload=market_payload,
                    news_items=[], account_balance=account_balance, risk_per_trade_pct=risk_per_trade_pct,
                    preliminary_analysis=analysis,
                )
            else:
                decision_prompt = base_prompt
            signal = brain.get_trade_signal(decision_prompt)
        except Exception as exc:
            logger.warning("Backtest: punto %s scartato per errore LLM: %s", ts, exc)
            continue

        if signal["action"] not in ("BUY", "SELL"):
            trades.append(BacktestTrade(
                timestamp=ts, symbol=symbol, action="HOLD", confidence=signal["confidence_percentage"],
                entry_price=entry_price, take_profit=None, stop_loss=None, lot_size=None,
                outcome="HOLD", exit_price=None, pips=None, r_multiple=None, reasoning=signal["reasoning"],
            ))
            continue

        if not meets_min_risk_reward(entry_price, signal["take_profit_price"], signal["stop_loss_price"]):
            trades.append(BacktestTrade(
                timestamp=ts, symbol=symbol, action="HOLD", confidence=signal["confidence_percentage"],
                entry_price=entry_price, take_profit=None, stop_loss=None, lot_size=None,
                outcome="HOLD", exit_price=None, pips=None, r_multiple=None,
                reasoning=signal["reasoning"] + " [Scartato dal risk manager: R:R insufficiente.]",
            ))
            continue

        lot_size = risk_manager.cap_llm_lot_size(
            llm_lot_size=signal["lot_size"], entry_price=entry_price,
            stop_loss_price=signal["stop_loss_price"], pip_size=pip_size,
        )

        future_df = enriched_df.iloc[idx + 1: idx + 1 + MAX_HOLDING_CANDLES]
        outcome, exit_price = simulate_outcome(
            signal["action"], signal["take_profit_price"], signal["stop_loss_price"], future_df,
        )

        risk_distance = abs(entry_price - signal["stop_loss_price"])
        pips = r_multiple = None
        if exit_price is not None and risk_distance > 0:
            realized = (exit_price - entry_price) if signal["action"] == "BUY" else (entry_price - exit_price)
            pips = round(realized / pip_size, 1)
            r_multiple = round(realized / risk_distance, 3)

        trades.append(BacktestTrade(
            timestamp=ts, symbol=symbol, action=signal["action"], confidence=signal["confidence_percentage"],
            entry_price=entry_price, take_profit=signal["take_profit_price"], stop_loss=signal["stop_loss_price"],
            lot_size=lot_size, outcome=outcome, exit_price=exit_price, pips=pips, r_multiple=r_multiple,
            reasoning=signal["reasoning"],
        ))

    return trades


def summarize(trades: list[BacktestTrade]) -> dict:
    """Statistiche aggregate: win rate ed espettanza in R vengono calcolate solo sui trade davvero presi (BUY/SELL)."""
    actionable = [t for t in trades if t.action in ("BUY", "SELL")]
    wins = [t for t in actionable if t.outcome == "TP"]
    losses = [t for t in actionable if t.outcome == "SL"]
    timeouts = [t for t in actionable if t.outcome == "TIMEOUT"]
    r_values = [t.r_multiple for t in actionable if t.r_multiple is not None]
    total_r = sum(r_values)

    return {
        "total_signals_evaluated": len(trades),
        "hold_count": len(trades) - len(actionable),
        "trades_taken": len(actionable),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "win_rate_pct": round(len(wins) / len(actionable) * 100, 1) if actionable else 0.0,
        "total_r": round(total_r, 2),
        "avg_r_per_trade": round(total_r / len(actionable), 3) if actionable else 0.0,
    }


def trades_to_dataframe(trades: list[BacktestTrade]) -> pd.DataFrame:
    return pd.DataFrame([asdict(t) for t in trades])
