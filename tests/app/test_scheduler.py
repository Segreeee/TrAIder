"""P3.28: scheduler allineato alla candela (D-010) e radice di composizione.
Orologio e sleep finti: nessuna attesa reale. Un ciclo oltre 12 minuti fa saltare la candela successiva
(registrata nel log); al riavvio si elabora solo l'ultima candela chiusa se ha meno di 5 minuti."""
import logging
from datetime import datetime, timedelta, timezone

from hypothesis import given
from hypothesis import strategies as st

from adapters.finnhub_news import FinnhubNews
from adapters.news_cache import CachedNews
from adapters.mt5_broker import Mt5Broker
from adapters.null_news import NullNews
from adapters.sim_broker import SimBroker
from app.compose import build_ports, mt5_init_kwargs
from app.config import Settings
from app.scheduler import last_closed_candle, next_run, run_loop
from tests.fakes import FakeMt5

T0 = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
TF, DELAY = 15, 10


@given(seconds=st.integers(0, 7 * 24 * 3600), delay=st.integers(0, 120))
def test_next_run_after_now_aligned_and_bounded(seconds, delay):
    now = T0 + timedelta(seconds=seconds)
    nxt = next_run(now, TF, delay)
    assert now < nxt <= now + timedelta(minutes=TF, seconds=delay)
    close = nxt - timedelta(seconds=delay)
    assert close.minute % TF == 0 and close.second == 0 and close.microsecond == 0


def test_last_closed_candle():
    assert last_closed_candle(T0 + timedelta(minutes=7, seconds=3), TF) == T0
    assert last_closed_candle(T0, TF) == T0


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.now += timedelta(seconds=seconds)


def test_loop_runs_once_per_candle_with_fake_clock():
    clock, seen = FakeClock(T0 + timedelta(minutes=7)), []
    run_loop(seen.append, clock, clock.sleep, TF, DELAY, max_cycles=4)
    assert seen == [T0 + timedelta(minutes=15 * k) for k in range(1, 5)]


def test_overrun_skips_and_logs(caplog):
    clock, seen = FakeClock(T0 + timedelta(minutes=7)), []

    def slow_first(candle):
        seen.append(candle)
        if len(seen) == 1:
            clock.now += timedelta(minutes=13)  # oltre 12 minuti

    with caplog.at_level(logging.WARNING):
        skipped = run_loop(slow_first, clock, clock.sleep, TF, DELAY, max_cycles=2)
    assert seen == [T0 + timedelta(minutes=15), T0 + timedelta(minutes=45)]
    assert skipped == [T0 + timedelta(minutes=30)] and "saltata" in caplog.text


def test_recovery_only_recent_candle():
    clock, seen = FakeClock(T0 + timedelta(minutes=3)), []  # ultima chiusura 3 minuti fa: si elabora
    run_loop(seen.append, clock, clock.sleep, TF, DELAY, max_cycles=1, recover=True)
    assert seen == [T0]

    clock, seen = FakeClock(T0 + timedelta(minutes=7)), []  # 7 minuti fa: troppo vecchia, si aspetta la prossima
    run_loop(seen.append, clock, clock.sleep, TF, DELAY, max_cycles=1, recover=True)
    assert seen == [T0 + timedelta(minutes=15)]


def test_cycle_exception_does_not_stop_loop(caplog):
    clock, seen = FakeClock(T0 + timedelta(minutes=7)), []

    def flaky(candle):
        seen.append(candle)
        if len(seen) == 1:
            raise RuntimeError("terminale disconnesso")

    run_loop(flaky, clock, clock.sleep, TF, DELAY, max_cycles=2)
    assert len(seen) == 2 and "terminale disconnesso" in caplog.text


# --- composizione ------------------------------------------------------------ #


def _build(tmp_path, **kw):
    cfg = Settings(_env_file=None, db_path=str(tmp_path / "data" / "t.db"), **kw)
    return build_ports(cfg, FakeMt5(T0), digest_of=lambda model: f"sha256:{model}")


def test_default_composition_uses_sim_broker_and_null_news(tmp_path):
    ports = _build(tmp_path)
    assert isinstance(ports.broker, SimBroker) and isinstance(ports.news, NullNews)
    assert ports.technical.model_digest == "sha256:gemma3:12b"
    assert (tmp_path / "data" / "t.db").exists()


def test_sim_broker_uses_configured_balance(tmp_path):
    assert _build(tmp_path, account_balance=2500).broker.account().equity == 2500


def test_double_consent_composes_mt5_broker(tmp_path):
    ports = _build(tmp_path, dry_run=False, allow_live_trading=True, commission_eur_per_lot=7.0)
    assert isinstance(ports.broker, Mt5Broker)


def test_finnhub_provider_composes_finnhub(tmp_path):
    news = _build(tmp_path, news_provider="finnhub", finnhub_api_key="k").news
    assert isinstance(news, CachedNews) and isinstance(news.inner, FinnhubNews)  # D-015: Finnhub dietro la cache


def test_mt5_init_kwargs_from_settings():
    cfg = Settings(_env_file=None, mt5_login="501", mt5_password="pw", mt5_server="Demo")
    assert mt5_init_kwargs(cfg) == {"login": 501, "password": "pw", "server": "Demo"}


def test_ollama_digest_reads_api_tags():
    import io
    import json
    from app.compose import ollama_digest
    payload = {"models": [{"name": "gemma3:12b", "model": "gemma3:12b", "digest": "abc123"}]}
    urls = []

    def opener(req, timeout):
        urls.append(req.full_url)
        return io.BytesIO(json.dumps(payload).encode())

    assert ollama_digest("http://localhost:11434/v1", "gemma3:12b", opener) == "abc123"
    assert urls == ["http://localhost:11434/api/tags"]
    import pytest
    with pytest.raises(RuntimeError, match="ollama pull"):
        ollama_digest("http://localhost:11434/v1", "qwen3:8b", opener)


def test_cycle_runs_every_symbol_then_resolves(monkeypatch, caplog):
    import app.compose as compose
    calls = []
    monkeypatch.setattr(compose, "run_once",
                        lambda symbol, close, ports, cfg, code_version: calls.append(("run", symbol, close, code_version)))

    def resolve(store, market, now, horizon=96):
        calls.append(("resolve", now))
        raise RuntimeError("barre non disponibili")

    monkeypatch.setattr(compose, "resolve_pending", resolve)
    cfg = Settings(_env_file=None, symbols="EURUSD,GBPUSD")
    from types import SimpleNamespace
    cycle = compose.make_cycle(cfg, ports=SimpleNamespace(store=None, market=None), code_version="abc", clock=lambda: T0 + timedelta(seconds=10))
    cycle(T0)  # l'errore della risoluzione è registrato, non propagato
    assert calls == [("run", "EURUSD", T0, "abc"), ("run", "GBPUSD", T0, "abc"), ("resolve", T0 + timedelta(seconds=10))]
    assert "barre non disponibili" in caplog.text


def test_main_rejects_invalid_config_before_touching_mt5(monkeypatch, caplog):
    import main
    monkeypatch.setenv("RISK_PER_TRADE_PCT", "99")  # fuori da (0, 5]
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    assert main.main([]) == 1
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "risk_per_trade_pct" in messages and "99" not in messages  # nomi dei campi, mai i valori


def test_cycle_resolves_with_configured_horizon(monkeypatch):
    # review di fine Fase 3 (R1): HORIZON_BARS era ignorato, la risoluzione usava sempre 96 barre
    import app.compose as compose
    from types import SimpleNamespace
    seen = []
    monkeypatch.setattr(compose, "run_once", lambda *a, **k: None)
    monkeypatch.setattr(compose, "resolve_pending", lambda store, market, now, horizon=96: seen.append(horizon))
    monkeypatch.setattr(compose, "reconcile_broker", lambda *a: 0)
    cfg = Settings(_env_file=None, symbols="EURUSD", horizon_bars=48)
    compose.make_cycle(cfg, ports=SimpleNamespace(store=None, market=None, broker=None), code_version="x",
                       clock=lambda: T0)(T0)
    assert seen == [48]


def test_live_news_provider_is_cached():
    # R3 / D-015: senza cache le notizie live non superano mai la regola anti-futuro
    from app.compose import _news
    from adapters.news_cache import CachedNews
    cfg = Settings(_env_file=None, news_provider="finnhub", finnhub_api_key="k")
    assert isinstance(_news(cfg), CachedNews)


def test_sim_broker_reads_positions_from_the_archive(tmp_path):
    # R4 / D-016: nel demone il broker simulato legge le posizioni aperte dall'archivio composto
    ports = _build(tmp_path)
    assert ports.broker.positions() == ports.store.open_sim_positions() == []
    assert ports.broker._open_positions == ports.store.open_sim_positions


class _FakeMt5Module:
    def __init__(self):
        self.shut = False

    def initialize(self, **kw):
        return True

    def last_error(self):
        return (0, "ok")

    def shutdown(self):
        self.shut = True


def _main_with(monkeypatch, fake_mt5, **patches):
    import sys
    import main
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)  # mai il modulo vero nei test
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    for name, value in patches.items():
        monkeypatch.setattr(main, name, value)
    return main.main(["--once"])


def test_main_logs_composition_failure_and_exits_1(monkeypatch, caplog):
    # review di fine Fase 3 (R9): Ollama giù o modello mancante uscivano come traceback grezzo, fuori dal log
    fake = _FakeMt5Module()

    def broken(cfg, mt5):
        raise RuntimeError("modello non trovato: esegui ollama pull gemma3:12b")

    assert _main_with(monkeypatch, fake, build_ports=broken) == 1
    assert "ollama pull" in caplog.text and fake.shut


def test_main_closes_the_archive(monkeypatch):
    from types import SimpleNamespace
    closed = []
    store = SimpleNamespace(close=lambda: closed.append(True))
    ports = SimpleNamespace(store=store, broker=SimpleNamespace())
    assert _main_with(monkeypatch, _FakeMt5Module(), build_ports=lambda cfg, mt5: ports,
                      make_cycle=lambda cfg, p, v: (lambda close: None), code_version=lambda: "x") == 0
    assert closed == [True]
