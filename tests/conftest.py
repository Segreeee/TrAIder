"""Guardie globali dei test: si applicano prima che qualunque modulo di test venga importato.

- Nessuna connessione di rete: ogni connect solleva OSError("rete bloccata ...").
- Il pacchetto MetaTrader5 reale non è importabile: i moduli che lo importano in try/except
  ricadono su mt5 = None, e un test non può mai parlare con un terminale vero.
- Hypothesis deterministico, senza deadline (i test non dipendono dal carico della macchina).
"""
import socket
import sys

from hypothesis import settings

sys.modules["MetaTrader5"] = None  # import MetaTrader5 -> ImportError

settings.register_profile("traider", derandomize=True, deadline=None)
settings.load_profile("traider")


def _blocked(*_args, **_kwargs):
    raise OSError("rete bloccata nei test: usare un adattatore finto")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
