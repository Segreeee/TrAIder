"""Guardie dell'ambiente di test: nessuna rete, nessun MetaTrader5 reale, hypothesis deterministico.

Le garanzie vengono da tests/conftest.py; questi test falliscono se qualcuno le toglie.
"""
import importlib
import socket

import pytest
from hypothesis import settings


def test_network_is_blocked():
    with pytest.raises(OSError, match="rete bloccata"):
        socket.create_connection(("example.com", 80), timeout=1)


def test_raw_socket_connect_is_blocked_even_to_a_listening_local_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError, match="rete bloccata"):
            client.connect(server.getsockname())
    finally:
        client.close()
        server.close()


def test_hypothesis_profile_is_deterministic():
    assert settings.default.derandomize is True
    assert settings.default.deadline is None


def test_real_metatrader5_cannot_be_imported():
    with pytest.raises(ImportError):
        importlib.import_module("MetaTrader5")


def test_real_configuration_is_hidden_from_tests():
    import os
    from app.config import Settings
    leaked = [n.upper() for n in Settings.model_fields if n.upper() in os.environ]
    assert leaked == [], f"variabili reali visibili ai test: {leaked}"  # solo i nomi, mai i valori


def test_real_env_file_is_not_read_by_tests():
    from app.config import Settings
    assert Settings().mt5_login == ""  # anche se il .env reale ha MT5_LOGIN


# --- P3.30: niente confidenza dichiarata, dashboard in sola lettura --- #

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def _imports(path):
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_module_imports_confidence():
    offenders = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.py")
                 if ".venv" not in p.parts and "core.confidence" in _imports(p)]
    assert offenders == []
    assert not (ROOT / "core" / "confidence.py").exists()


def test_dashboard_has_no_llm_or_broker_imports():
    forbidden = {"core.qwen_brain", "core.ensemble", "core.executor", "core.prompt_builder", "core.data_feed",
                 "core.news_feed", "adapters.llm_openai", "adapters.mt5_broker", "adapters.mt5_data", "MetaTrader5"}
    assert _imports(ROOT / "dashboard.py") & forbidden == set()
