"""P3.04 (T-007): stima dello scarto tra ora del server MT5 e UTC, senza rete né terminale.

MT5 restituisce il campo `time` delle barre come epoch nell'ora del server (non UTC).
L'apertura della barra in formazione, confrontata con l'ora UTC corrente, rivela lo scarto.
"""
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.clock import server_offset_hours, to_utc

NOW = datetime(2026, 11, 23, 10, 7, 30, tzinfo=timezone.utc)


def _forming_bar_open(now_utc: datetime, offset_h: int, tf_min: int) -> int:
    """Epoch 'ora del server' dell'apertura della barra in formazione."""
    server_naive_epoch = int(now_utc.timestamp()) + offset_h * 3600
    return server_naive_epoch - server_naive_epoch % (tf_min * 60)


@pytest.mark.parametrize("offset", [0, 2, 3])
def test_offset_zero_plus2_plus3(offset):
    assert server_offset_hours(_forming_bar_open(NOW, offset, 15), NOW, 15) == offset


def test_offset_negative():
    assert server_offset_hours(_forming_bar_open(NOW, -5, 15), NOW, 15) == -5


def test_returns_none_when_bar_too_old():
    stale = _forming_bar_open(NOW - timedelta(days=2, minutes=37), 2, 15)  # weekend, mercato chiuso
    assert server_offset_hours(stale, NOW, 15) is None


def test_rejects_naive_now():
    with pytest.raises(ValueError):
        server_offset_hours(0, datetime(2026, 1, 1), 15)


@given(
    seconds=st.integers(min_value=0, max_value=10 * 365 * 86400),
    offset=st.integers(min_value=-12, max_value=14),
    tf=st.sampled_from([1, 5, 15, 30]),
)
def test_offset_recovered_for_any_time(seconds, offset, tf):
    now = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    assert server_offset_hours(_forming_bar_open(now, offset, tf), now, tf) == offset


@given(epoch=st.integers(min_value=0, max_value=2_000_000_000), offset=st.integers(min_value=-12, max_value=14))
def test_roundtrip_to_utc(epoch, offset):
    assert to_utc(epoch + offset * 3600, offset) == datetime.fromtimestamp(epoch, tz=timezone.utc)
