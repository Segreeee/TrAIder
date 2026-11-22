"""
Stato reale del conto letto da MT5: capitale, posizioni aperte del bot, risultato del giorno.

Senza MT5 (DRY_RUN su macchine senza terminale, test) ricade sul saldo configurato,
nessuna posizione e risultato del giorno nullo.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AccountState:
    equity: float
    open_positions: list = field(default_factory=list)  # [(symbol, "BUY"/"SELL")]
    day_pnl: float = 0.0  # realizzato oggi + aperto, solo operazioni del bot (magic)


def read_account_state(mt5_module, magic: int, fallback_balance: float, now: Optional[datetime] = None) -> AccountState:
    if mt5_module is None:
        return AccountState(equity=fallback_balance, open_positions=[], day_pnl=0.0)

    info = mt5_module.account_info()
    equity = float(info.equity) if info is not None else fallback_balance

    positions = [p for p in (mt5_module.positions_get() or []) if getattr(p, "magic", None) == magic]
    open_positions = [(p.symbol, "BUY" if p.type == 0 else "SELL") for p in positions]
    floating = sum(float(p.profit) for p in positions)

    now = now or datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = [d for d in (mt5_module.history_deals_get(day_start, now) or []) if getattr(d, "magic", None) == magic]
    realized = sum(float(d.profit) + float(d.commission) + float(d.swap) for d in deals)

    return AccountState(equity=equity, open_positions=open_positions, day_pnl=round(realized + floating, 2))
