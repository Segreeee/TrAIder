"""Re-export temporaneo: le regole di portafoglio vivono in domain/exposure.py (rimosso in P3.31)."""
from domain.exposure import (  # noqa: F401
    check_new_position,
    currency_exposure,
    daily_loss_limit_reached,
    split_symbol,
)
