"""Contratto della porta Broker: lo stesso controllo gira sul broker simulato e (P3.16) su quello MT5,
quest'ultimo solo su conto demo e solo con conferma esplicita dell'utente."""
from domain.types import Direction
from ports import Fill, OrderRequest


def check_broker(broker, symbol: str, bid: float, ask: float):
    pip = 0.01 if symbol[3:6] == "JPY" else 0.0001

    zero = broker.submit(OrderRequest(symbol, Direction.BUY, 0.0, sl=ask - 20 * pip, tp=ask + 30 * pip))
    assert isinstance(zero, Fill) and not zero.accepted, "lotto 0 accettato"

    inverted = broker.submit(OrderRequest(symbol, Direction.BUY, 0.01, sl=ask + 20 * pip, tp=ask - 30 * pip))
    assert not inverted.accepted, "BUY con TP/SL invertiti accettato"
    assert broker.positions() == [], "un ordine rifiutato ha aperto una posizione"

    fill = broker.submit(OrderRequest(symbol, Direction.BUY, 0.01, sl=ask - 20 * pip, tp=ask + 30 * pip))
    assert fill.accepted and fill.mode in {"sim", "mt5"}
    assert fill.fill_price > 0 and fill.spread >= 0

    held = broker.positions()
    assert [(p.symbol, p.direction, p.lots) for p in held] == [(symbol, Direction.BUY, 0.01)]
