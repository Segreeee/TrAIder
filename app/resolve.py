"""Risoluzione virtuale di tutti i candidati in attesa, eseguiti o no (Q-004).

Si usano solo le barre M15 aperte dalla chiusura del candidato in poi. Primo tra TP e SL vince
(SL se nella stessa barra); senza tocchi si aspetta fino a HORIZON barre, poi TIMEOUT alla chiusura.
R netto con il costo registrato al momento della decisione. resolved_at = chiusura della barra d'uscita.
Barre bid: i BUY escono sul bid, i SELL sull'ask (bid + spread della barra) (T-010).
Limite noto del simulatore (rischio 2 di ALTERNATIVE.md): nessuno slippage sull'uscita.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from domain.outcome import first_hit, realized_result
from domain.pip import pip_size, pip_value_eur
from ports import Broker, MarketData, Outcome, SignalStore

log = logging.getLogger(__name__)
HORIZON, MAX_BARS, MARGIN = 96, 5000, 5
M15 = timedelta(minutes=15)


def resolve_pending(store: SignalStore, market: MarketData, now: datetime, horizon: int = HORIZON) -> int:
    """Risolve ciò che si può risolvere adesso; restituisce quanti esiti ha scritto."""
    by_symbol = defaultdict(list)
    for cid, rec in store.pending_candidates():
        by_symbol[rec.candidate.symbol].append((cid, rec))

    written = 0
    for symbol, items in by_symbol.items():
        oldest = min(rec.candidate.candle_close_utc for _, rec in items)
        count = min(int((now - oldest) / M15) + MARGIN, MAX_BARS)
        bars = market.closed_bars(symbol, "M15", count)
        for cid, rec in items:
            c = rec.candidate
            if bars.empty or bars["timestamp"].iloc[0] >= c.candle_close_utc:
                # l'esito è definitivo: meglio nessun esito che uno calcolato su barre che non seguono il candidato
                log.warning("%s: le barre lette non coprono la chiusura %s del candidato %s, non lo risolvo",
                            symbol, c.candle_close_utc, cid)
                continue
            future = bars[bars["timestamp"] >= c.candle_close_utc].head(horizon).reset_index(drop=True)
            spread = future["spread"] * pip_size(symbol) / 10  # punti MT5 -> prezzo; usato per le uscite SELL
            hit = first_hit(c.direction.value, c.tp, c.sl, future, spread)
            if hit is not None:
                result, exit_price, i = hit
            elif len(future) >= horizon:
                last = float(future["close"].iloc[-1])
                exit_price = last if c.direction.value == "BUY" else last + float(spread.iloc[-1])  # SELL esce all'ask
                result, i = "TIMEOUT", horizon - 1
            else:
                continue  # né tocchi né orizzonte completo: si riprova al prossimo ciclo
            r = realized_result(c.direction.value, c.entry, exit_price, c.sl, pip_size(symbol), rec.cost_pips)
            exit_close = future["timestamp"].iloc[i].to_pydatetime() + M15
            written += store.record_outcome(cid, Outcome(result, exit_price, r["r_multiple"], r["r_multiple_gross"],
                                                         "virtuale", exit_close))
    return written


def reconcile_broker(store: SignalStore, broker: Broker, market: MarketData) -> int:
    """Esiti del broker per gli ordini MT5 chiusi (P3.34), accanto a quelli virtuali; restituisce quanti ne scrive.
    R misurato dal prezzo di fill e sulla sua distanza dallo stop; R netto con commissione e swap veri."""
    written = 0
    for cid, rec, ticket, lots, fill_price in store.open_broker_trades():
        closed = broker.closed_trade(ticket)
        if closed is None:
            continue  # ancora aperta: si riprova al prossimo ciclo
        c, pip = rec.candidate, pip_size(rec.candidate.symbol)
        gross = realized_result(c.direction.value, fill_price, closed.exit_price, c.sl, pip, 0.0)["r_multiple_gross"]
        # ponytail: cambio EUR di adesso, non dell'ingresso; scarto < 1% sul valore del pip in un orizzonte di 24 h
        risk_eur = abs(fill_price - c.sl) / pip * pip_value_eur(c.symbol, market.eur_quote_rate(c.symbol), lots)
        net = round(gross + (closed.commission_eur + closed.swap_eur) / risk_eur, 3)
        written += store.record_broker_outcome(cid, closed, gross, net)
    return written
