"""P3.10: regole di portafoglio. Invarianti: mai due posizioni sullo stesso simbolo,
mai oltre il massimo di posizioni, mai oltre il limite di esposizione per valuta."""
from hypothesis import given
from hypothesis import strategies as st

from domain.exposure import check_new_position, currency_exposure, daily_loss_limit_reached

# --- casi noti (stesse asserzioni di ExposureTest legacy) -------------------- #


def test_currency_exposure_counts_both_legs():
    assert currency_exposure([("EURUSD", "BUY"), ("USDJPY", "BUY")]) == {"EUR": 1, "USD": 0, "JPY": -1}


def test_same_symbol_twice_is_blocked():
    ok, reason = check_new_position("EURUSD", "BUY", [("EURUSD", "BUY")], 3, 1)
    assert not ok and "EURUSD" in reason


def test_correlated_dollar_bet_is_blocked():
    ok, reason = check_new_position("GBPUSD", "BUY", [("EURUSD", "BUY")], 3, 1)
    assert not ok and "USD" in reason


def test_hedging_trade_is_allowed():
    assert check_new_position("USDJPY", "BUY", [("EURUSD", "BUY")], 3, 1)[0]


def test_max_open_positions():
    ok, reason = check_new_position("AUDNZD", "BUY", [("EURUSD", "BUY"), ("USDJPY", "BUY")], 2, 5)
    assert not ok and "2" in reason


def test_daily_loss_limit():
    assert daily_loss_limit_reached(day_pnl=-30, equity=970, limit_pct=3)
    assert not daily_loss_limit_reached(day_pnl=-29, equity=971, limit_pct=3)
    assert not daily_loss_limit_reached(day_pnl=50, equity=1050, limit_pct=3)


def test_core_exposure_reexports_domain():
    import core.exposure as legacy
    assert legacy.check_new_position is check_new_position


# --- proprietà --------------------------------------------------------------- #
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "EURGBP", "EURJPY"]
position = st.tuples(st.sampled_from(SYMBOLS), st.sampled_from(["BUY", "SELL"]))
book = st.lists(position, max_size=6, unique_by=lambda p: p[0])


@given(open_positions=book, new=position)
def test_never_two_positions_same_symbol(open_positions, new):
    if any(s == new[0] for s, _ in open_positions):
        assert not check_new_position(new[0], new[1], open_positions, 10, 10)[0]


@given(open_positions=book, new=position, max_open=st.integers(min_value=1, max_value=6))
def test_never_more_than_max_open(open_positions, new, max_open):
    if check_new_position(new[0], new[1], open_positions, max_open, 10)[0]:
        assert len(open_positions) + 1 <= max_open


@given(open_positions=book, new=position, limit=st.integers(min_value=1, max_value=3))
def test_accepted_position_keeps_every_currency_within_limit(open_positions, new, limit):
    within = all(abs(v) <= limit for v in currency_exposure(open_positions).values())
    if within and check_new_position(new[0], new[1], open_positions, 10, limit)[0]:
        after = currency_exposure(open_positions + [new])
        assert all(abs(v) <= limit for v in after.values())
