"""P3.13: broker simulato e doppio consenso. Il broker reale si costruisce solo con
dry_run=False E allow_live=True; qualunque altra combinazione dà il simulato."""
import ast
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from adapters.sim_broker import SimBroker
from domain.types import Direction
from ports import Broker, OrderRequest, build_broker
from tests.contracts.broker_contract import check_broker

BID, ASK = 1.10000, 1.10008


def _sim():
    return SimBroker(quote=lambda symbol: (BID, ASK))


def test_sim_broker_honours_contract():
    check_broker(_sim(), "EURUSD", BID, ASK)
    assert isinstance(_sim(), Broker)


def test_sim_fills_buy_at_ask_and_sell_at_bid():
    sim = _sim()
    buy = sim.submit(OrderRequest("EURUSD", Direction.BUY, 0.1, sl=1.0980, tp=1.1030))
    sell = sim.submit(OrderRequest("GBPUSD", Direction.SELL, 0.1, sl=1.1020, tp=1.0970))
    assert (buy.fill_price, sell.fill_price) == (ASK, BID)
    assert buy.spread == pytest.approx(ASK - BID) and buy.mode == "sim"


class _Live:
    """Segnaposto del broker reale: qui non fa nulla, serve solo a vedere se viene costruito."""


@given(dry_run=st.booleans(), allow_live=st.booleans())
def test_mt5_factory_called_iff_double_consent(dry_run, allow_live):
    calls = []

    def make_live():
        calls.append(1)
        return _Live()

    broker = build_broker(dry_run=dry_run, allow_live=allow_live, make_live=make_live, make_sim=_sim)
    expected_live = (not dry_run) and allow_live
    assert (len(calls) == 1) == expected_live
    assert isinstance(broker, _Live) == expected_live


@pytest.mark.parametrize("dry_run, allow_live", [("false", True), (False, "true"), (0, True), (None, True)])
def test_non_boolean_flags_are_rejected(dry_run, allow_live):
    # "false" è una stringa vera in Python: un flag letto male non deve mai aprire il conto reale
    with pytest.raises(TypeError):
        build_broker(dry_run=dry_run, allow_live=allow_live, make_live=_Live, make_sim=_sim)


def test_sim_broker_never_imports_metatrader5():
    tree = ast.parse(Path("adapters/sim_broker.py").read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("MetaTrader5" in m or m.startswith("core") for m in imported)
