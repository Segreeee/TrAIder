"""P3.29: le garanzie dei 30 test legacy, puntate sui moduli nuovi.

Ogni garanzia è già coperta da un test nel modulo nuovo (tabella LEGACY sotto). Questo file controlla che
quei test esistano ancora, così la cancellazione dei moduli legacy (P3.31) non può perderne nessuno, e
aggiunge le due garanzie che non avevano ancora un test.

Cambi di asserzione confermati dall'utente all'approvazione del piano:
- (a) caso normale del rischio: 0.50 -> 0.55 lotti (il vecchio test conteneva il pip fisso a 10 EUR);
- (b) ritirati i test del giudice decisore (prompt "ATTENZIONE", verdetti nel prompt): il giudice
      decisore non esiste più (D-012);
- (c) "analista fallito / tutti giù" non ripiega più sul giudice: diventa "caratteristica mancante" (D-002).

Fuori da qui:
- YahooNewsFeed (3 test) resta in tests/test_news_feed.py finché non si decide T-002;
- CostsTest.test_summary_reports_gross_and_net va in P5.02 (evaluation/metrics.py, R lordo e netto).
"""
import re
from pathlib import Path

import pytest

from app.extractors import AnalystView
from app.run_once import run_once

TESTS = Path(__file__).resolve().parents[1]

# (test legacy, file di destinazione relativo a tests/, test di destinazione)
LEGACY = [
    ("NewsFeed.default_provider_returns_no_news", "app/test_scheduler.py", "test_default_composition_uses_sim_broker_and_null_news"),
    ("NewsFeed.mock_allowed_only_in_dry_run", "app/test_config.py", "test_mock_news_live_fails"),
    ("NewsFeed.unknown_provider_is_rejected", "app/test_config.py", "test_unknown_provider_fails"),
    ("ClosedCandles.fetch_ohlcv_skips_forming_candle", "adapters/test_mt5_data.py", "test_fetch_skips_forming_candle"),
    ("Risk.lot_below_minimum_means_no_trade", "domain/test_risk.py", "test_lot_below_minimum_means_no_trade"),
    ("Risk.zero_stop_distance_means_no_trade", "domain/test_risk.py", "test_zero_stop_means_no_trade"),
    ("Risk.normal_case_unchanged (a: 0.55)", "domain/test_risk.py", "test_eurusd_normal_case"),
    ("Risk.llm_lot_capped_to_zero", "regression/test_legacy_guarantees.py", "test_lot_never_comes_from_the_llm"),
    ("Exposure.currency_exposure_counts_both_legs", "domain/test_exposure.py", "test_currency_exposure_counts_both_legs"),
    ("Exposure.same_symbol_twice_is_blocked", "domain/test_exposure.py", "test_same_symbol_twice_is_blocked"),
    ("Exposure.correlated_dollar_bet_is_blocked", "domain/test_exposure.py", "test_correlated_dollar_bet_is_blocked"),
    ("Exposure.hedging_trade_is_allowed", "domain/test_exposure.py", "test_hedging_trade_is_allowed"),
    ("Exposure.max_open_positions", "domain/test_exposure.py", "test_max_open_positions"),
    ("Exposure.daily_loss_limit", "domain/test_exposure.py", "test_daily_loss_limit"),
    ("Account.without_mt5_uses_configured_balance", "app/test_scheduler.py", "test_sim_broker_uses_configured_balance"),
    ("Account.reads_equity_positions_and_today_pnl", "adapters/test_mt5_broker.py", "test_reads_equity_positions_and_today_pnl_for_our_magic_only"),
    ("Costs.costs_reduce_r_multiple", "domain/test_costs_outcome.py", "test_costs_reduce_r_multiple"),
    ("Costs.costs_make_losses_bigger", "domain/test_costs_outcome.py", "test_costs_make_losses_bigger"),
    ("ActiveAnalysts.macro_excluded_without_news", "app/test_run_once.py", "test_macro_only_with_visible_news"),
    ("ExecutorRealPrice.spread_breaks_risk_reward", "adapters/test_mt5_broker.py", "test_order_not_sent_when_spread_breaks_risk_reward"),
    ("Ensemble.collects_both_analysts", "app/test_run_once.py", "test_macro_only_with_visible_news"),
    ("Ensemble.failed_analyst_is_skipped (c)", "app/test_run_once.py", "test_llm_down_records_cycle_with_missing_features"),
    ("Ensemble.all_down_returns_empty (c)", "regression/test_legacy_guarantees.py", "test_all_analysts_down_cycle_still_done"),
    ("Ensemble.think_block_stripped", "adapters/test_llm_openai.py", "test_think_block_stripped"),
]


@pytest.mark.parametrize("legacy, path, name", LEGACY, ids=[row[0] for row in LEGACY])
def test_legacy_guarantee_still_has_its_test(legacy, path, name):
    source = (TESTS / path).read_text(encoding="utf-8")
    assert re.search(rf"^def {name}\(", source, re.MULTILINE), f"{legacy}: manca {path}::{name}"


def test_lot_never_comes_from_the_llm():
    # Il vecchio executor riduceva a 0 il lotto proposto dall'LLM; ora l'LLM non può proprio proporlo.
    view = {"direzione": 1, "forza": 2, "orizzonte": "intraday", "motivazioni": ["x"]}
    with pytest.raises(ValueError):
        AnalystView.model_validate({**view, "lot_size": 0.5})


def test_all_analysts_down_cycle_still_done():
    from tests.app.test_run_once import CLOSE, NewsItem, _cfg, _ports, timedelta
    from tests.fakes import FakeLlm
    news = NewsItem("BCE invariata", "x", CLOSE - timedelta(hours=2), CLOSE - timedelta(hours=1))
    down = lambda: FakeLlm([ConnectionError("ollama giù")] * 10)  # noqa: E731
    ports = _ports(news_items=[news], tech=down(), macro=down())
    report = run_once("EURUSD", CLOSE, ports, _cfg())
    assert report.status == "done"
    assert report.features["tecnico"] is None and report.features["macro"] is None
    assert sorted(report.llm_invalid) == ["macro", "tecnico"]
    assert ports.broker.positions() == []
