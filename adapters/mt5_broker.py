"""Broker MetaTrader5: l'unico file che può inviare ordini al terminale (solo conto demo finché
l'utente non decide altrimenti). Il modulo mt5 è iniettato; questo file non importa MetaTrader5.

Difesa in profondità, oltre al doppio consenso di ports.build_broker:
- il costruttore rifiuta di partire se live_allowed non è esattamente True;
- submit ricontrolla lotto, direzione dei livelli e R:R al prezzo reale (ask/bid) prima della richiesta.
"""
import logging
from datetime import datetime, timezone
from typing import Callable

from domain.costs import distance_pips
from domain.pip import pip_size
from domain.types import Direction, levels_consistent
from ports import AccountState, ClosedTrade, Fill, OrderRequest, Position

log = logging.getLogger(__name__)


class Mt5Broker:
    def __init__(self, mt5, magic: int, live_allowed: bool, min_rr: float = 1.5,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        if live_allowed is not True:
            raise PermissionError("broker MT5 costruito senza consenso esplicito agli ordini reali")
        self._mt5, self._magic, self._min_rr, self._clock = mt5, magic, min_rr, clock

    def submit(self, order: OrderRequest) -> Fill:
        tick = self._mt5.symbol_info_tick(order.symbol)
        if tick is None:
            return Fill("mt5", False, 0.0, 0.0, None, f"nessun tick: {self._mt5.last_error()}")
        bid, ask = float(tick.bid), float(tick.ask)
        buy = order.direction is Direction.BUY
        price = ask if buy else bid

        def refuse(reason: str) -> Fill:
            log.warning("ordine %s %s rifiutato: %s", order.direction.value, order.symbol, reason)
            return Fill("mt5", False, 0.0, ask - bid, None, reason)

        if order.lots <= 0:
            return refuse("lotto non positivo")
        if not levels_consistent(order.direction.value, price, order.tp, order.sl):
            return refuse(f"TP/SL dal lato sbagliato del prezzo {price}")
        pip = pip_size(order.symbol)
        d_sl = distance_pips(price, order.sl, pip)
        if d_sl == 0:
            return refuse("stop a meno di 0.1 pip dal prezzo")
        rr = distance_pips(order.tp, price, pip) / d_sl
        if rr < self._min_rr:
            return refuse(f"R:R al prezzo reale {rr:.2f} < {self._min_rr}")

        m = self._mt5
        request = {
            "action": m.TRADE_ACTION_DEAL, "symbol": order.symbol, "volume": order.lots,
            "type": m.ORDER_TYPE_BUY if buy else m.ORDER_TYPE_SELL, "price": price,
            "sl": order.sl, "tp": order.tp, "deviation": 10, "magic": self._magic,
            "comment": "TrAIder", "type_time": m.ORDER_TIME_GTC, "type_filling": m.ORDER_FILLING_IOC,
        }
        result = m.order_send(request)  # unico punto del progetto che invia ordini al terminale
        if result is None or result.retcode != m.TRADE_RETCODE_DONE:
            code = getattr(result, "retcode", None)
            return refuse(f"rifiutato dal terminale (retcode {code}): {getattr(result, 'comment', m.last_error())}")
        ticket = int(result.order)
        entry = [d for d in self._deals(ticket) if d.entry == self.DEAL_ENTRY_IN]
        commission = sum(float(d.commission) for d in entry) if entry else None
        return Fill("mt5", True, float(getattr(result, "price", 0) or price), ask - bid, ticket, commission=commission)

    DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1

    def _deals(self, ticket: int) -> list:
        return [d for d in (self._mt5.history_deals_get(position=ticket) or [])
                if getattr(d, "magic", None) == self._magic]

    def closed_trade(self, ticket: int):
        deals = self._deals(ticket)
        out = [d for d in deals if d.entry == self.DEAL_ENTRY_OUT]
        if not out:
            return None  # aperta, o ticket non nostro
        return ClosedTrade(exit_price=float(out[-1].price), profit_eur=sum(float(d.profit) for d in deals),
                           commission_eur=sum(float(d.commission) for d in deals),
                           swap_eur=sum(float(d.swap) for d in deals))

    def _our_positions(self):
        return [p for p in (self._mt5.positions_get() or []) if getattr(p, "magic", None) == self._magic]

    def positions(self) -> list[Position]:
        return [Position(p.symbol, Direction.BUY if p.type == 0 else Direction.SELL, float(p.volume),
                         float(p.price_open), float(p.sl), float(p.tp), int(p.ticket)) for p in self._our_positions()]

    def account(self) -> AccountState:
        """Capitale, posizioni del bot e P&L del giorno (UTC) con commissioni e swap, solo per il nostro magic."""
        info = self._mt5.account_info()
        if info is None:
            raise RuntimeError(f"account_info non disponibile: {self._mt5.last_error()}")
        ours = self._our_positions()
        now = self._clock()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = [d for d in (self._mt5.history_deals_get(day_start, now) or []) if getattr(d, "magic", None) == self._magic]
        realized = sum(float(d.profit) + float(d.commission) + float(d.swap) for d in deals)
        floating = sum(float(p.profit) for p in ours)
        return AccountState(float(info.equity), [(p.symbol, "BUY" if p.type == 0 else "SELL") for p in ours],
                            round(realized + floating, 2))
