"""Guardie globali dei test: si applicano prima che qualunque modulo di test venga importato.

- Nessuna connessione di rete: ogni connect solleva OSError("rete bloccata ...").
- Il pacchetto MetaTrader5 reale non è importabile: i moduli che lo importano in try/except
  ricadono su mt5 = None, e un test non può mai parlare con un terminale vero.
- Hypothesis deterministico, senza deadline (i test non dipendono dal carico della macchina).
- Nessuna variabile d'ambiente della configurazione reale (credenziali MT5, chiavi) è visibile ai test.
"""
import socket
import sys

import pytest
from hypothesis import settings

sys.modules["MetaTrader5"] = None  # import MetaTrader5 -> ImportError

settings.register_profile("traider", derandomize=True, deadline=None)
settings.load_profile("traider")


def _blocked(*_args, **_kwargs):
    raise OSError("rete bloccata nei test: usare un adattatore finto")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked


@pytest.fixture(autouse=True)
def _no_real_configuration(monkeypatch):
    """Nessun test vede la configurazione reale: VS Code può caricare il .env nelle variabili
    d'ambiente del terminale, e un'asserzione fallita stamperebbe credenziali vere (è successo)."""
    from app.config import Settings
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    # anche il file .env reale: un test che lo vuole deve passare _env_file esplicitamente
    monkeypatch.setitem(Settings.model_config, "env_file", None)


@pytest.fixture(autouse=True)
def _no_real_dashboard_write(monkeypatch):
    """Un ciclo di make_cycle nei test non scrive mai la dashboard nel percorso di default (data/dashboard.html,
    accanto all'archivio reale): review di P7.01. I test che la vogliono la sostituiscono di nuovo o chiamano
    report.dashboard.write_dashboard con percorsi in tmp_path."""
    import app.compose
    monkeypatch.setattr(app.compose, "write_dashboard", lambda *a, **k: None)
