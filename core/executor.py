"""
Broker Execution.

Modulo che "esegue" il segnale di trading validato:
- in modalita' DRY_RUN (default) stampa a console l'ordine simulato,
- altrimenti invia l'ordine reale a MT5 tramite order_send.

Tenuto volutamente semplice per l'MVP: nessuna gestione di posizioni multiple,
trailing stop o parziali. Un solo ordine a mercato per ciclo decisionale.
"""
import logging
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None

from config.settings import settings
from core.qwen_brain import TradeSignal
from core.risk_manager import compute_risk_reward_ratio, meets_min_risk_reward

logger = logging.getLogger(__name__)


class ExecutorError(Exception):
    """Errore durante l'invio/esecuzione dell'ordine."""


class OrderExecutor:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    def execute(self, symbol: str, signal: TradeSignal) -> Optional[dict]:
        """
        Esegue (o simula) l'ordine derivato dal segnale.
        Ritorna il risultato dell'esecuzione (dict) oppure None se action == HOLD.
        """
        if signal["action"] == "HOLD" or not signal.get("lot_size"):
            logger.info("Segnale HOLD o lotto nullo: nessun ordine da eseguire.")
            self._print_order_summary(symbol, signal, status="SKIPPED (HOLD)")
            return None

        if self.dry_run or mt5 is None:
            self._print_order_summary(symbol, signal, status="SIMULATED (dry-run)")
            return {"status": "simulated"}

        return self._send_order_to_mt5(symbol, signal)

    # ------------------------------------------------------------------ #
    def _send_order_to_mt5(self, symbol: str, signal: TradeSignal) -> dict:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ExecutorError(f"Impossibile ottenere il tick corrente per {symbol}.")

        order_type = mt5.ORDER_TYPE_BUY if signal["action"] == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick.ask if signal["action"] == "BUY" else tick.bid

        # Il R:R era stato verificato sulla chiusura dell'ultima candela; l'ordine parte
        # invece al prezzo ask/bid attuale (spread incluso). Con stop di pochi pip la
        # differenza puo' far scendere il rapporto sotto la soglia: si ricontrolla qui.
        if not meets_min_risk_reward(price, signal["take_profit_price"], signal["stop_loss_price"]):
            rr = compute_risk_reward_ratio(price, signal["take_profit_price"], signal["stop_loss_price"])
            logger.warning("Ordine %s %s non inviato: R:R al prezzo reale %.5f e' %.2f.", signal["action"], symbol, price, rr)
            self._print_order_summary(symbol, signal, status=f"SKIPPED (R:R reale {rr:.2f})")
            return {"status": "skipped", "reason": f"R:R al prezzo reale {rr:.2f}"}

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": signal["lot_size"],
            "type": order_type,
            "price": price,
            "sl": signal["stop_loss_price"],
            "tp": signal["take_profit_price"],
            "deviation": 10,
            "magic": settings.magic_number,
            "comment": "TrAIder-Qwen-MVP",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise ExecutorError(f"Invio ordine fallito: {result}")

        logger.info("Ordine eseguito con successo su MT5: %s", result)
        self._print_order_summary(symbol, signal, status="EXECUTED on MT5")
        return {"status": "executed", "mt5_result": result._asdict()}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _print_order_summary(symbol: str, signal: TradeSignal, status: str) -> None:
        print("=" * 60)
        print(f"[EXECUTOR] {status}")
        print(f"  Symbol            : {symbol}")
        print(f"  Action            : {signal['action']}")
        print(f"  Confidence        : {signal['confidence_percentage']}%")
        print(f"  Lot size          : {signal['lot_size']}")
        print(f"  Take Profit       : {signal['take_profit_price']}")
        print(f"  Stop Loss         : {signal['stop_loss_price']}")
        print(f"  Reasoning         : {signal['reasoning']}")
        print("=" * 60)
