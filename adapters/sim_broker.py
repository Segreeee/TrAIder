"""Broker simulato: è il default (D-006). Riempie al prezzo corrente con lo spread
(ask per BUY, bid per SELL). Le posizioni aperte vengono dall'archivio (D-016) o, senza archivio,
dalla memoria. Non importa MetaTrader5."""
from typing import Callable, Optional

from domain.types import Direction, levels_consistent
from ports import AccountState, Fill, OrderRequest, Position


class SimBroker:
    def __init__(self, quote: Callable[[str], tuple[float, float]], equity: float = 10_000.0,
                 commission_eur_per_lot: float = 0.0,
                 open_positions: Optional[Callable[[], list[Position]]] = None):
        self._quote = quote  # simbolo -> (bid, ask)
        # D-016: nel demone le posizioni aperte vengono dall'archivio (eseguite, non ancora risolte);
        # senza archivio restano in memoria e non si chiudono (solo test e prove isolate).
        self._open_positions = open_positions
        self._equity = equity
        self._commission = commission_eur_per_lot  # andata e ritorno: metà all'ingresso, come i deal MT5
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
        if self._open_positions is None:  # con l'archivio la posizione nasce da record_execution
            self._positions.append(Position(order.symbol, order.direction, order.lots, price, order.sl, order.tp, ticket))
        return Fill("sim", True, price, ask - bid, ticket, commission=-self._commission / 2 * order.lots)

    def closed_trade(self, ticket: int) -> None:
        return None  # il broker simulato non segue i prezzi: l'esito è solo quello virtuale

    def positions(self) -> list[Position]:
        return self._open_positions() if self._open_positions else list(self._positions)

    def account(self) -> AccountState:
        """Capitale configurato (ACCOUNT_BALANCE), posizioni simulate, P&L del giorno 0:
        il broker simulato non segue i prezzi; gli esiti li calcola la risoluzione virtuale."""
        return AccountState(self._equity, [(p.symbol, p.direction.value) for p in self.positions()], 0.0)