"""Risoluzione virtuale di tutti i candidati in attesa, eseguiti o no (Q-004).

Si usano solo le barre M15 aperte dalla chiusura del candidato in poi. Primo tra TP e SL vince
(SL se nella stessa barra); senza tocchi si aspetta fino a HORIZON barre, poi TIMEOUT alla chiusura.
R netto con il costo registrato al momento della decisione. resolved_at = chiusura della barra d'uscita.
Barre bid: i BUY escono sul bid, i SELL sull'ask (bid + spread della barra) (T-010).
Limite noto del simulatore (rischio 2 di ALTERNATIVE.md): nessuno slippage sull'uscita.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from domain.outcome import first_hit, realized_result
from domain.pip import pip_size
from ports import MarketData, Outcome, SignalStore

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
