"""Broker simulato: è il default (D-006). Riempie al prezzo corrente con lo spread
(ask per BUY, bid per SELL) e tiene le posizioni in memoria. Non importa MetaTrader5."""
from typing import Callable

from domain.types import Direction, levels_consistent
from ports import AccountState, Fill, OrderRequest, Position


class SimBroker:
    def __init__(self, quote: Callable[[str], tuple[float, float]], equity: float = 10_000.0):
        self._quote = quote  # simbolo -> (bid, ask)
        self._equity = equity
        self._positions: list[Position] = []
        self._next_ticket = 1

    def submit(self, order: OrderRequest) -> Fill:
        bid, ask = self._quote(order.symbol)
        price = ask if order.direction is Direction.BUY else bid
        if order.lots <= 0:
            return Fill("sim", False, 0.0, ask - bid, None, "lotto non positivo")
        if not levels_consistent(order.direction.value, price, order.tp, order.sl):
            return Fill("sim", False, 0.0, ask - bid, None, "TP/SL dal lato sbagliato del prezzo")
        ticket, self._next_ticket = self._next_ticket, self._next_ticket + 1
        self._positions.append(Position(order.symbol, order.direction, order.lots, price, order.sl, order.tp, ticket))
        return Fill("sim", True, price, ask - bid, ticket)

    def positions(self) -> list[Position]:
        return list(self._positions)

    def account(self) -> AccountState:
        """Capitale configurato (ACCOUNT_BALANCE), posizioni simulate, P&L del giorno 0:
        il broker simulato non segue i prezzi; gli esiti li calcola la risoluzione virtuale."""
        return AccountState(self._equity, [(p.symbol, p.direction.value) for p in self._positions], 0.0)