"""Tipi di dominio. Un Candidate con geometria invertita o orario senza fuso non può esistere."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class HoldReason(str, Enum):
    """Motivi chiusi per cui un candidato non diventa un ordine (salvati in candidates.hold_reason)."""
    NO_CANDIDATE = "NO_CANDIDATE"
    GATE_EV = "GATE_EV"
    SAME_SYMBOL = "SAME_SYMBOL"
    EXPOSURE = "EXPOSURE"
    MAX_POSITIONS = "MAX_POSITIONS"
    DAILY_LOSS = "DAILY_LOSS"
    LOT_BELOW_MIN = "LOT_BELOW_MIN"
    LLM_INVALID = "LLM_INVALID"


def levels_consistent(action: str, entry_price: float, take_profit_price: float, stop_loss_price: float) -> bool:
    """TP e SL dal lato giusto dell'ingresso: BUY -> SL < entry < TP; SELL -> TP < entry < SL."""
    if action == "BUY":
        return stop_loss_price < entry_price < take_profit_price
    if action == "SELL":
        return take_profit_price < entry_price < stop_loss_price
    return False


@dataclass(frozen=True)
class Candidate:
    symbol: str
    direction: Direction
    entry: float
    sl: float
    tp: float
    candle_close_utc: datetime

    def __post_init__(self):
        if self.candle_close_utc.tzinfo is None:
            raise ValueError("candle_close_utc deve avere un fuso orario")
        if not levels_consistent(self.direction.value, self.entry, self.tp, self.sl):
            raise ValueError(f"geometria invertita per {self.direction.value}: entry={self.entry} sl={self.sl} tp={self.tp}")

    @property
    def d_sl(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def d_tp(self) -> float:
        return abs(self.tp - self.entry)
