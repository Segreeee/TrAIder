"""P3.26: decisione su un candidato. Ordine: LLM non valido → perdita giornaliera → gate EV_5 →
portafoglio (stesso simbolo, massimo posizioni, esposizione) → Kelly e lotto. Invariante: il rischio
del lotto finale (costo incluso) non supera mai RISK_PER_TRADE_PCT."""
from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.config import Settings
from app.decide import Context, decide
from app.variants import Estimate
from domain.types import Candidate, Direction, HoldReason

T0 = datetime(2026, 3, 2, tzinfo=timezone.utc)
CAND = Candidate("EURUSD", Direction.BUY, 1.1000, 1.0980, 1.1030, T0)  # 20 / 30 pip
EDGE = Estimate(p=0.60, p5=0.55, model="logistica")
NO_EDGE = Estimate(p=0.40, p5=0.33, model="beta")


def _ctx(**kw):
    base = dict(equity=10_000.0, positions=[], day_pnl=0.0, cost_pips=1.0, pip_value_eur=9.0909,
                cfg=Settings(_env_file=None))
    return Context(**{**base, **kw})


def test_trade_when_edge():
    d = decide(CAND, EDGE, _ctx())
    assert d.decision == "TRADE" and d.hold_reason is None and d.lot > 0
    assert d.ev5 > 0 and d.p_star == pytest.approx(21 / 50)


def test_gate_closed_gives_GATE_EV():
    d = decide(CAND, NO_EDGE, _ctx())
    assert (d.decision, d.hold_reason, d.lot) == ("HOLD", HoldReason.GATE_EV, 0.0)


def test_llm_invalid_comes_first():
    assert decide(CAND, EDGE, _ctx(), llm_invalid=True).hold_reason is HoldReason.LLM_INVALID


def test_daily_loss_reason():
    assert decide(CAND, EDGE, _ctx(day_pnl=-300.0, equity=9_700.0)).hold_reason is HoldReason.DAILY_LOSS


@pytest.mark.parametrize("positions, reason", [
    ([("EURUSD", "SELL")], HoldReason.SAME_SYMBOL),
    ([("AUDNZD", "BUY"), ("USDJPY", "BUY"), ("EURGBP", "SELL")], HoldReason.MAX_POSITIONS),
    ([("GBPUSD", "BUY")], HoldReason.EXPOSURE),
])
def test_exposure_blocks_with_reason(positions, reason):
    assert decide(CAND, EDGE, _ctx(positions=positions)).hold_reason is reason


def test_lot_zero_gives_LOT_BELOW_MIN():
    assert decide(CAND, EDGE, _ctx(equity=50.0)).hold_reason is HoldReason.LOT_BELOW_MIN


def test_cost_above_tp_distance_has_no_edge():
    assert decide(CAND, EDGE, _ctx(cost_pips=35.0)).hold_reason is HoldReason.GATE_EV


@given(equity=st.floats(100, 1e6), risk=st.floats(0.05, 5.0), p=st.floats(0.45, 0.95),
       cost=st.floats(0, 5), pip_value=st.floats(0.5, 15))
def test_final_lot_respects_risk_limit(equity, risk, p, cost, pip_value):
    cfg = Settings(_env_file=None, risk_per_trade_pct=risk, max_lot=100.0)
    d = decide(CAND, Estimate(p=p, p5=p - 0.02, model="logistica"),
               _ctx(equity=equity, cost_pips=cost, pip_value_eur=pip_value, cfg=cfg))
    assert d.lot == 0.0 or d.lot >= cfg.min_lot
    assert d.lot * (20 + cost) * pip_value <= equity * risk / 100 * (1 + 1e-9)
