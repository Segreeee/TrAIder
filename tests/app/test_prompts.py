"""P3.24: prompt separati (D-004). Il tecnico non vede notizie, il macro non vede prezzi;
nessuno vede conto, rischio o confidenza. La versione del prompt è l'hash del template."""
import re
from datetime import datetime, timedelta, timezone

from app.features import add_indicators
from app.prompts import (MACRO_PROMPT_VERSION, TECHNICAL_PROMPT_VERSION, build_macro_prompt,
                         build_technical_prompt, prompt_version)
from ports import NewsItem
from tests.fakes import FakeMarketData

NOW = datetime(2026, 3, 2, 12, 7, tzinfo=timezone.utc)
BARS = add_indicators(FakeMarketData(now=NOW, tf_minutes=15).closed_bars("EURUSD", "M15", 60))
NEWS = [NewsItem("BCE lascia i tassi invariati", "reuters", NOW - timedelta(hours=3), NOW - timedelta(hours=2)),
        NewsItem("Inflazione USA in calo", "ap", NOW - timedelta(hours=1), NOW - timedelta(minutes=30))]


def _text(prompt):
    system, user = prompt
    return system + "\n" + user


def test_technical_prompt_has_prices_and_trend_but_no_headlines():
    text = _text(build_technical_prompt("EURUSD", BARS, htf_trend="rialzista"))
    assert f"{BARS['close'].iloc[-1]:.5f}" in text and "rialzista" in text
    assert not any(n.headline in text for n in NEWS)


def test_macro_prompt_has_headlines_and_no_prices():
    text = _text(build_macro_prompt("EURUSD", NEWS))
    assert all(n.headline in text for n in NEWS)
    assert not re.search(r"\d\.\d{4,}", text)  # nessun prezzo a 4+ decimali
    assert not any(f"{v:.5f}" in text for v in BARS[["open", "high", "low", "close"]].to_numpy().ravel())


def test_macro_prompt_without_news_says_so():
    assert "nessuna notizia" in _text(build_macro_prompt("EURUSD", [])).lower()


def test_no_account_or_confidence_in_prompts():
    for text in (_text(build_technical_prompt("EURUSD", BARS, "ribassista")), _text(build_macro_prompt("EURUSD", NEWS))):
        lowered = text.lower()
        assert not any(w in lowered for w in ("confidenza", "probabilit", "saldo", "equity", "lotto", "rischio"))


def test_prompts_ask_for_the_closed_schema():
    for text in (_text(build_technical_prompt("EURUSD", BARS, "laterale")), _text(build_macro_prompt("EURUSD", NEWS))):
        assert all(k in text for k in ("direzione", "forza", "orizzonte", "motivazioni"))


def test_prompt_version_changes_with_template():
    assert prompt_version("a {x}") != prompt_version("b {x}")
    assert prompt_version("a {x}") == prompt_version("a {x}")
    assert TECHNICAL_PROMPT_VERSION.startswith("tecnico-") and MACRO_PROMPT_VERSION.startswith("macro-")
    assert TECHNICAL_PROMPT_VERSION != MACRO_PROMPT_VERSION


def test_macro_prompt_states_a_length_limit_within_the_schema():
    """T-014: il macro scriveva più frasi in una motivazione (354 caratteri) e lo schema la scartava;
    a temperatura 0 il retry ripete la stessa risposta, quindi il limite va detto nel prompt."""
    from app.extractors import AnalystView
    limit = AnalystView.model_fields["motivazioni"].annotation.__args__[0].__metadata__[0].max_length
    stated = re.search(r"(\d+) caratteri", _text(build_macro_prompt("EURUSD", NEWS)))
    assert stated and int(stated.group(1)) <= limit * 2 // 3  # margine: il modello non conta i caratteri
