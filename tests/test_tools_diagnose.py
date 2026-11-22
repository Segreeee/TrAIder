"""P3.05: lo script di diagnosi del fuso passa le credenziali del .env a initialize, non stampa mai
la password e usa solo funzioni di lettura. Nei test MT5 è finto (conftest blocca il pacchetto reale)."""
from datetime import datetime, timezone

import numpy as np

from app.config import Settings
from tools.diagnose_mt5_tz import init_kwargs, main

SECRET = "pw-segretissima"


def _cfg(**kw):
    return Settings(_env_file=None, **kw)


def test_init_kwargs_from_settings():
    cfg = _cfg(mt5_login="5012345", mt5_password=SECRET, mt5_server="Pepperstone-Demo", mt5_path="C:/MT5/terminal64.exe")
    assert init_kwargs(cfg) == {"path": "C:/MT5/terminal64.exe", "login": 5012345, "password": SECRET,
                                "server": "Pepperstone-Demo"}


def test_init_kwargs_empty_when_not_configured():
    assert init_kwargs(_cfg()) == {}


class FakeMt5:
    TIMEFRAME_M15 = 15

    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def initialize(self, **kwargs):
        self.calls.append(("initialize", kwargs))
        return self.ok

    def last_error(self):
        return (-6, "Terminal: Authorization failed")

    def symbol_select(self, symbol, enable):
        self.calls.append(("symbol_select", symbol))
        return True

    def copy_rates_from_pos(self, symbol, tf, start, count):
        self.calls.append(("copy_rates_from_pos", start, count))
        server_now = int(datetime.now(timezone.utc).timestamp()) + 2 * 3600
        return np.array([(server_now // 900 * 900,)], dtype=[("time", "i8")])

    def shutdown(self):
        self.calls.append(("shutdown",))


def test_main_passes_credentials_and_prints_offset(capsys):
    mt5 = FakeMt5()
    cfg = _cfg(mt5_login="5012345", mt5_password=SECRET, mt5_server="Pepperstone-Demo")
    assert main(["EURUSD"], mt5, cfg) == 0
    assert mt5.calls[0] == ("initialize", init_kwargs(cfg))
    out = capsys.readouterr().out
    assert "+2 ore" in out and SECRET not in out
    assert {c[0] for c in mt5.calls} <= {"initialize", "symbol_select", "copy_rates_from_pos", "shutdown"}


def test_failed_initialize_explains_without_password(capsys):
    cfg = _cfg(mt5_login="5012345", mt5_password=SECRET, mt5_server="Pepperstone-Demo")
    assert main([], FakeMt5(ok=False), cfg) == 1
    out = capsys.readouterr().out
    assert "Authorization failed" in out and "login" in out.lower() and SECRET not in out
