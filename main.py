"""
Entry point del demone headless AI Trading Agent.

Ciclo operativo:
1. Connessione a MT5 e download OHLCV (solo candele chiuse) + calcolo indicatori
   (RSI/EMA/MACD/ATR/BB) e del trend sul timeframe superiore.
2. Recupero notizie dalla sorgente configurata (NEWS_PROVIDER; default nessuna).
3. Stato reale del conto: capitale, posizioni aperte del bot, risultato del giorno.
   Se il limite di perdita giornaliero e' raggiunto, il ciclo si ferma qui.
4. Costruzione prompt (fase 1, senza analisi preliminare).
5. Analisti locali (Ollama) emettono un verdetto indipendente; un terzo modello
   locale (giudice) decide. Senza notizie l'analista macro e' escluso. Fallback: giudice da solo in due fasi.
6. Risk gate: R:R minimo, una posizione per simbolo, esposizione per valuta,
   lotto calcolato sul capitale reale (nessun trade se sotto il lotto minimo).
7. Esecuzione (o simulazione) dell'ordine, con R:R ricontrollato al prezzo reale.
8. Attesa fino al ciclo successivo.

Nessuna interfaccia grafica: tutto logga su stdout e su file di log.
"""
import logging
import sys
import time
from logging.handlers import RotatingFileHandler

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None

from config.settings import settings
from core.account import read_account_state
from core.data_feed import DataFeedError, MarketDataFeed
from core.ensemble import active_analysts, build_analysts, build_judge, collect_persona_signals, judge_signal
from core.executor import ExecutorError, OrderExecutor
from core.exposure import check_new_position, daily_loss_limit_reached
from core.news_feed import NewsFeed, build_news_feed
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


def _downgrade_to_hold(signal: dict, reason: str) -> None:
    signal["action"] = "HOLD"
    signal["lot_size"] = 0.0
    signal["reasoning"] += f" [Declassato a HOLD dal risk manager: {reason}.]"
    logger.warning("Segnale declassato a HOLD: %s", reason)


def run_trading_cycle(
    data_feed: MarketDataFeed,
    news_feed: NewsFeed,
    brain: QwenBrain,
    analysts: dict,
    executor: OrderExecutor,
) -> None:
    """Esegue un singolo ciclo completo: dati -> conto -> LLM -> risk -> esecuzione."""
    symbol = settings.symbol

    # 1. Dati di mercato (candele chiuse) + indicatori + trend sul timeframe superiore
    raw_df = data_feed.fetch_ohlcv()
    enriched_df = data_feed.add_indicators(raw_df)
    market_payload = data_feed.to_compact_payload(enriched_df)
    htf_trend = data_feed.get_higher_timeframe_trend(symbol=symbol)

    # 2. Notizie (lista vuota se NEWS_PROVIDER=none)
    news_items = news_feed.get_latest_news(symbol)

    # 3. Stato reale del conto e limite di perdita giornaliero (prima di spendere chiamate LLM)
    account = read_account_state(mt5, settings.magic_number, settings.account_balance)
    if daily_loss_limit_reached(account.day_pnl, account.equity, settings.daily_loss_limit_pct):
        logger.warning(
            "Limite di perdita giornaliero raggiunto (risultato oggi %.2f su capitale %.2f, limite %.1f%%): "
            "nessuna nuova operazione fino a domani.", account.day_pnl, account.equity, settings.daily_loss_limit_pct,
        )
        return

    # 4. Prompt (fase 1: senza analisi preliminare)
    base_prompt = build_user_prompt(
        symbol=symbol,
        timeframe=settings.timeframe,
        market_payload=market_payload,
        news_items=news_items,
        account_balance=account.equity,
        risk_per_trade_pct=settings.risk_per_trade_pct,
        htf_trend=htf_trend,
    )

    # 5. Analisti + giudice. Senza notizie reali l'analista macro non partecipa.
    analysts_now = active_analysts(analysts, has_news=bool(news_items))
    persona_signals = collect_persona_signals(base_prompt, analysts_now)
    if persona_signals:
        for name, sig in persona_signals.items():
            logger.info("%s: %s (TP %s, SL %s)", name, sig["action"], sig["take_profit_price"], sig["stop_loss_price"])
        signal = judge_signal(
            brain, persona_signals, symbol=symbol, market_payload=market_payload,
            news_items=news_items, htf_trend=htf_trend,
            expected_analysts=len(analysts_now), account_balance=account.equity,
        )
    else:
        logger.warning("Nessun analista locale disponibile: uso il flusso single-model.")
        analysis = brain.run_reasoning_pass(base_prompt)
        decision_prompt = build_user_prompt(
            symbol=symbol,
            timeframe=settings.timeframe,
            market_payload=market_payload,
            news_items=news_items,
            account_balance=account.equity,
            risk_per_trade_pct=settings.risk_per_trade_pct,
            htf_trend=htf_trend,
            preliminary_analysis=analysis,
        )
        signal = brain.get_trade_signal(decision_prompt)
    logger.info("Segnale finale: %s", signal)

    # 6. Risk gate
    if signal["action"] in ("BUY", "SELL"):
        entry_price = market_payload["indicators"]["last_close"]
        if not meets_min_risk_reward(entry_price, signal["take_profit_price"], signal["stop_loss_price"]):
            actual_rr = compute_risk_reward_ratio(entry_price, signal["take_profit_price"], signal["stop_loss_price"])
            _downgrade_to_hold(signal, f"R:R reale {actual_rr:.2f} sotto la soglia minima {MIN_RISK_REWARD_RATIO}")
        else:
            allowed, reason = check_new_position(
                symbol, signal["action"], account.open_positions,
                settings.max_open_positions, settings.max_currency_exposure,
            )
            if not allowed:
                _downgrade_to_hold(signal, reason)
            else:
                risk_manager = RiskManager(account.equity, settings.risk_per_trade_pct)
                capped_lot = risk_manager.cap_llm_lot_size(
                    llm_lot_size=signal["lot_size"],
                    entry_price=entry_price,
                    stop_loss_price=signal["stop_loss_price"],
                    pip_size=pip_size_for_symbol(symbol),
                )
                if capped_lot <= 0:
                    _downgrade_to_hold(signal, "anche il lotto minimo supererebbe il rischio massimo per operazione")
                else:
                    if capped_lot != signal["lot_size"]:
                        logger.info(
                            "Lot size proposto da Qwen (%.2f) ricalcolato/limitato dal RiskManager a %.2f",
                            signal["lot_size"], capped_lot,
                        )
                    signal["lot_size"] = capped_lot

    # 7. Esecuzione
    executor.execute(symbol, signal)


def main() -> None:
    logger.info(
        "Avvio TrAIder MVP | symbol=%s timeframe=%s dry_run=%s news=%s",
        settings.symbol, settings.timeframe, settings.dry_run, settings.news_provider,
    )

    try:
        news_feed = build_news_feed(settings.news_provider, settings.dry_run)
    except ValueError as exc:
        logger.error("Configurazione non valida: %s", exc)
        sys.exit(1)

    data_feed = MarketDataFeed()
    brain = build_judge()
    analysts = build_analysts()
    executor = OrderExecutor(dry_run=settings.dry_run, allow_live_trading=settings.allow_live_trading)

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
