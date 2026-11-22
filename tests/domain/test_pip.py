"""P3.07: valore del pip per coppia, conto in EUR (sostituisce i 10 USD fissi).

Valore di 1 pip per 1 lotto standard (100 000 unità della valuta base), in valuta quotata:
pip_size * 100 000. In EUR si divide per il cambio EUR/quotata (1 se la quotata è EUR).
"""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.pip import conversion_symbol, pip_size, pip_value_eur


def test_eurusd_eur_account():
    assert pip_value_eur("EURUSD", eur_quote_rate=1.10) == pytest.approx(9.0909, abs=1e-4)


def test_usdjpy_eur_account():
    # 1 pip USDJPY = 0.01 * 100 000 = 1000 JPY; con EURJPY 165 -> 6.0606 EUR
    assert pip_value_eur("USDJPY", eur_quote_rate=165.0) == pytest.approx(6.0606, abs=1e-4)


def test_eurgbp_eur_account():
    # 1 pip EURGBP = 10 GBP; con EURGBP 0.85 -> 11.7647 EUR
    assert pip_value_eur("EURGBP", eur_quote_rate=0.85) == pytest.approx(11.7647, abs=1e-4)


def test_quote_eur_needs_no_conversion():
    assert conversion_symbol("GBPEUR") is None
    assert pip_value_eur("GBPEUR", eur_quote_rate=1.0) == pytest.approx(10.0)


def test_pip_size():
    assert pip_size("EURUSD") == 0.0001
    assert pip_size("USDJPY") == 0.01
    assert pip_size("eurjpy") == 0.01


def test_symbol_suffix_ignored():
    assert pip_size("USDJPY.a") == 0.01
    assert conversion_symbol("GBPUSD.r") == "EURUSD"


def test_nonpositive_rate_raises():
    with pytest.raises(ValueError):
        pip_value_eur("EURUSD", eur_quote_rate=0)


def test_conversion_symbol():
    assert conversion_symbol("GBPUSD") == "EURUSD"
    assert conversion_symbol("USDJPY") == "EURJPY"
    assert conversion_symbol("AUDCAD") == "EURCAD"
    assert conversion_symbol("EURGBP") == "EURGBP"


@given(lots=st.floats(min_value=0.01, max_value=50), rate=st.floats(min_value=0.5, max_value=200))
def test_pip_value_linear_in_lots(lots, rate):
    assert pip_value_eur("EURUSD", rate, lots) == pytest.approx(lots * pip_value_eur("EURUSD", rate))
