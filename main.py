"""
Entry point del demone headless AI Trading Agent.

Ciclo operativo:
1. Connessione a MT5 e download OHLCV + calcolo indicatori (RSI/EMA/MACD/ATR/BB)
   e del trend sul timeframe superiore.
2. Recupero notizie (mock).
3. Costruzione prompt (fase 1, senza analisi preliminare).
4. Due analisti locali (Ollama) emettono un verdetto indipendente; un terzo
   modello locale (giudice) decide. Fallback: giudice da solo in due fasi.
5. Validazione/ricalcolo del lot_size via RiskManager.
6. Esecuzione (o simulazione) dell'ordine.
7. Attesa fino al ciclo successivo.

Nessuna interfaccia grafica: tutto logga su stdout e su file di log.
"""
import logging
import sys
import time
from logging.handlers import RotatingFileHandler

from config.settings import settings
from core.data_feed import DataFeedError, MarketDataFeed
from core.ensemble import build_analysts, build_judge, collect_persona_signals, judge_signal
from core.executor import ExecutorError, OrderExecutor
from core.news_feed import YahooNewsFeed
from core.prompt_builder import build_user_prompt
from core.qwen_brain import QwenBrain, QwenBrainError
from core.risk_manager import (
    MIN_RISK_REWARD_RATIO,
    RiskManager,
    compute_risk_reward_ratio,
    meets_min_risk_reward,
    pip_size_for_symbol,
)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("traider")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler("logs/traider.log", maxBytes=2_000_000, backupCount=3)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()


def run_trading_cycle(
    data_feed: MarketDataFeed,
    news_feed: YahooNewsFeed,
    brain: QwenBrain,
    analysts: dict,
    executor: OrderExecutor,
) -> None:
    """Esegue un singolo ciclo completo: dati -> LLM -> risk -> esecuzione."""

    # 1. Dati di mercato + indicatori (+ trend sul timeframe superiore)
    raw_df = data_feed.fetch_ohlcv()
    enriched_df = data_feed.add_indicators(raw_df)
    market_payload = data_feed.to_compact_payload(enriched_df)
    htf_trend = data_feed.get_higher_timeframe_trend(symbol=settings.symbol)

    # 2. Notizie
    news_items = news_feed.get_latest_news(settings.symbol)

    # 3. Prompt (fase 1: senza analisi preliminare)
    base_prompt = build_user_prompt(
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        market_payload=market_payload,
        news_items=news_items,
        account_balance=settings.account_balance,
        risk_per_trade_pct=settings.risk_per_trade_pct,
        htf_trend=htf_trend,
    )

    # 4. LLM-as-a-judge: gli analisti locali (Ollama) emettono un verdetto
    # indipendente, il giudice arbitra. Se nessun analista risponde, ricade sul
    # flusso single-model a due fasi (analisi libera + verdetto strutturato).
    persona_signals = collect_persona_signals(base_prompt, analysts)
    if persona_signals:
        for name, sig in persona_signals.items():
            logger.info("%s: %s (TP %s, SL %s)", name, sig["action"], sig["take_profit_price"], sig["stop_loss_price"])
        signal = judge_signal(
            brain, persona_signals, symbol=settings.symbol, market_payload=market_payload,
            news_items=news_items, htf_trend=htf_trend,
        )
    else:
        logger.warning("Nessun analista locale disponibile: uso il flusso single-model.")
        analysis = brain.run_reasoning_pass(base_prompt)
        decision_prompt = build_user_prompt(
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            market_payload=market_payload,
            news_items=news_items,
            account_balance=settings.account_balance,
            risk_per_trade_pct=settings.risk_per_trade_pct,
            htf_trend=htf_trend,
            preliminary_analysis=analysis,
        )
        signal = brain.get_trade_signal(decision_prompt)
    logger.info("Segnale finale: %s", signal)

    # 5. Risk management: il rapporto rischio/rendimento viene ricalcolato (non
    # ci si fida del valore dichiarato da Qwen nel campo reasoning) e il trade
    # viene declassato a HOLD se non rispetta il minimo richiesto; altrimenti
    # il lot_size viene comunque ricalcolato/limitato in autonomia.
    if signal["action"] in ("BUY", "SELL"):
        entry_price = market_payload["indicators"]["last_close"]
        if not meets_min_risk_reward(entry_price, signal["take_profit_price"], signal["stop_loss_price"]):
            actual_rr = compute_risk_reward_ratio(entry_price, signal["take_profit_price"], signal["stop_loss_price"])
            logger.warning(
                "Segnale %s scartato: R:R reale %.2f sotto la soglia minima %.2f (nonostante il reasoning dichiarasse il contrario).",
                signal["action"], actual_rr, MIN_RISK_REWARD_RATIO,
            )
            signal["action"] = "HOLD"
            signal["lot_size"] = 0.0
            signal["reasoning"] += (
                f" [Segnale declassato a HOLD dal risk manager: R:R reale {actual_rr:.2f} "
                f"sotto la soglia minima {MIN_RISK_REWARD_RATIO}.]"
            )
        else:
            risk_manager = RiskManager(settings.account_balance, settings.risk_per_trade_pct)
            capped_lot = risk_manager.cap_llm_lot_size(
                llm_lot_size=signal["lot_size"],
                entry_price=entry_price,
                stop_loss_price=signal["stop_loss_price"],
                pip_size=pip_size_for_symbol(settings.symbol),
            )
            if capped_lot != signal["lot_size"]:
                logger.info(
                    "Lot size proposto da Qwen (%.2f) ricalcolato/limitato dal RiskManager a %.2f",
                    signal["lot_size"], capped_lot,
                )
            signal["lot_size"] = capped_lot

    # 6. Esecuzione
    executor.execute(settings.symbol, signal)


def main() -> None:
    logger.info("Avvio TrAIder MVP | symbol=%s timeframe=%s dry_run=%s", settings.symbol, settings.timeframe, settings.dry_run)

    data_feed = MarketDataFeed()
    news_feed = YahooNewsFeed()
    brain = build_judge()
    analysts = build_analysts()
    executor = OrderExecutor(dry_run=settings.dry_run)

    try:
        data_feed.connect()
    except DataFeedError as exc:
        logger.error("Impossibile avviare il demone: %s", exc)
        sys.exit(1)

    try:
        while True:
            try:
                run_trading_cycle(data_feed, news_feed, brain, analysts, executor)
            except DataFeedError as exc:
                logger.error("Errore nel recupero dati di mercato: %s", exc)
            except QwenBrainError as exc:
                logger.error("Errore nella decisione dell'LLM: %s", exc)
            except ExecutorError as exc:
                logger.error("Errore nell'esecuzione dell'ordine: %s", exc)
            except Exception:
                logger.exception("Errore imprevisto nel ciclo di trading.")

            logger.info("Ciclo completato. In attesa di %d secondi...", settings.loop_interval_seconds)
            time.sleep(settings.loop_interval_seconds)

    except KeyboardInterrupt:
        logger.info("Interruzione manuale ricevuta (Ctrl+C). Arresto in corso...")
    finally:
        data_feed.shutdown()
        logger.info("TrAIder arrestato.")


if __name__ == "__main__":
    main()
