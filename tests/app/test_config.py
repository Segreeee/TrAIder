"""P3.21: configurazione con pydantic-settings (D-011). Default sicuri, validazione all'avvio,
segreti mai in chiaro, nessuna lettura all'import."""
import pytest
from pydantic import ValidationError

import app.config as config_module
from app.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # le variabili della shell non devono influenzare i test
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def _settings(**kw):
    return Settings(_env_file=None, **kw)


def test_defaults_are_safe():
    s = _settings()
    assert s.dry_run is True and s.allow_live_trading is False
    assert s.news_provider == "none"
    assert s.remote_judge_base_url is None and s.remote_judge_api_key is None
    assert 0 < s.risk_per_trade_pct <= 1.0


def test_no_settings_instance_at_import():
    assert not any(isinstance(v, Settings) for v in vars(config_module).values())


def test_live_without_second_flag_fails():
    with pytest.raises(ValidationError, match="secondo consenso"):
        _settings(dry_run=False)


def test_live_with_both_flags_is_accepted():
    s = _settings(dry_run=False, allow_live_trading=True, commission_eur_per_lot=7.0)
    assert not s.dry_run and s.allow_live_trading


def test_string_flags_parsed_strictly(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    with pytest.raises(ValidationError):  # "false" letto come False, quindi manca il secondo consenso
        Settings(_env_file=None)
    monkeypatch.setenv("DRY_RUN", "forse")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_mock_news_live_fails():
    with pytest.raises(ValidationError, match="mock"):
        _settings(dry_run=False, allow_live_trading=True, news_provider="mock", commission_eur_per_lot=7.0)


def test_unknown_provider_fails():
    with pytest.raises(ValidationError):
        _settings(news_provider="yahoo")


def test_finnhub_requires_key():
    with pytest.raises(ValidationError, match="FINNHUB_API_KEY"):
        _settings(news_provider="finnhub")


def test_remote_judge_all_or_nothing():
    with pytest.raises(ValidationError, match="giudice remoto"):
        _settings(remote_judge_base_url="https://example.invalid/v1")
    s = _settings(remote_judge_base_url="https://example.invalid/v1", remote_judge_model="m",
                  remote_judge_api_key="k")
    assert s.remote_judge_model == "m"


def test_live_requires_explicit_commission():
    # costo sottostimato = rischio sottostimato: fuori da DRY_RUN la commissione va dichiarata
    with pytest.raises(ValidationError, match="COMMISSION_EUR_PER_LOT"):
        _settings(dry_run=False, allow_live_trading=True)


def test_repr_hides_secrets():
    s = _settings(mt5_password="pw-segreta", finnhub_api_key="fh-segreta", news_provider="finnhub")
    text = repr(s) + str(s) + str(s.model_dump())
    assert "pw-segreta" not in text and "fh-segreta" not in text


def test_config_hash_excludes_secrets_and_is_stable():
    a = _settings(mt5_password="uno")
    b = _settings(mt5_password="due")
    assert a.config_hash() == b.config_hash() == _settings().config_hash()
    assert _settings(risk_per_trade_pct=0.5).config_hash() != a.config_hash()


@pytest.mark.parametrize("value", [0, -1, 5.01])
def test_risk_pct_out_of_range_fails(value):
    with pytest.raises(ValidationError):
        _settings(risk_per_trade_pct=value)


def test_reads_environment(monkeypatch):
    monkeypatch.setenv("SYMBOLS", "eurusd, gbpusd")
    monkeypatch.setenv("RISK_PER_TRADE_PCT", "0.5")
    s = Settings(_env_file=None)
    assert s.symbols == ("EURUSD", "GBPUSD") and s.risk_per_trade_pct == 0.5


def test_empty_values_in_env_file_use_defaults(tmp_path):
    env = tmp_path / ".env"
    env.write_text("DRY_RUN=\nRISK_PER_TRADE_PCT=\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.dry_run is True and s.risk_per_trade_pct == 1.0


def test_old_variable_names_in_env_file_fail(tmp_path):
    # un .env non aggiornato deve fermare l'avvio, non essere ignorato in silenzio
    env = tmp_path / ".env"
    env.write_text("QWEN_API_KEY=x\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        Settings(_env_file=env)


def test_dashboard_path_does_not_change_the_series():
    # P6.03: il test in avanti è in corso; un campo nuovo che cambiasse config_hash aprirebbe una nuova serie (§7).
    # 27918a0189865d27 è l'hash della configurazione di default prima di questo campo.
    custom = Settings(_env_file=None, dashboard_path="C:/Users/utente/OneDrive/traider/dashboard.html")
    assert custom.config_hash() == Settings(_env_file=None).config_hash() == "27918a0189865d27"
    assert "dashboard_path" not in custom.public_config()  # percorso personale: non va in archivio
    assert Settings(_env_file=None).dashboard_path == "data/dashboard.html"
