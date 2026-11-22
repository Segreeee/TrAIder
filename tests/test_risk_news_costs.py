"""Test delle correzioni: notizie, candele chiuse, rischio, esposizione, costi.

Eseguire con: python -m unittest discover tests
Nessun test richiede MetaTrader5, Ollama o rete: MT5 e' sostituito da finti oggetti.
"""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from core.account import AccountState, read_account_state
from core.backtester import realized_result, summarize, BacktestTrade
from core.exposure import check_new_position, currency_exposure, daily_loss_limit_reached
from core.news_feed import MockNewsFeed, NullNewsFeed, build_news_feed
from core.prompt_builder import build_manager_prompt
from core.risk_manager import RiskManager


# --------------------------------------------------------------------------- #
# 1. Notizie: niente notizie inventate quando si opera davvero
# --------------------------------------------------------------------------- #
class NewsFeedTest(unittest.TestCase):
    def test_default_provider_returns_no_news(self):
        feed = build_news_feed("none", dry_run=False)
        self.assertIsInstance(feed, NullNewsFeed)
        self.assertEqual(feed.get_latest_news("EURUSD"), [])

    def test_mock_allowed_only_in_dry_run(self):
        self.assertIsInstance(build_news_feed("mock", dry_run=True), MockNewsFeed)
        with self.assertRaises(ValueError):
            build_news_feed("mock", dry_run=False)

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            build_news_feed("telepatia", dry_run=True)

    def test_judge_prompt_does_not_warn_when_macro_is_off_by_design(self):
        sig = {"action": "BUY", "confidence_percentage": 60, "take_profit_price": 1.12,
               "stop_loss_price": 1.09, "reasoning": "x"}
        market = {"indicators": {"last_close": 1.1}, "candles": []}
        prompt = build_manager_prompt(
            symbol="EURUSD", timeframe="M15", market_payload=market, news_items=[],
            account_balance=1000, risk_per_trade_pct=1, htf_trend=None,
            persona_signals={"Tecnico": sig}, expected_analysts=1,
        )
        self.assertNotIn("ATTENZIONE", prompt)


# --------------------------------------------------------------------------- #
# 2. Candele: in live si usano solo candele chiuse
# --------------------------------------------------------------------------- #
class ClosedCandlesTest(unittest.TestCase):
    def test_fetch_ohlcv_skips_forming_candle(self):
        import numpy as np
        import core.data_feed as df_mod

        calls = []

        class FakeMt5:
            TIMEFRAME_M15 = 15

            def symbol_select(self, symbol, enable):
                return True

            def copy_rates_from_pos(self, symbol, tf, start, count):
                calls.append(start)
                dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
                         ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")]
                return np.array([(1_700_000_000, 1.0, 1.1, 0.9, 1.05, 10, 1, 0)], dtype=dtype)

            def last_error(self):
                return None

        original = df_mod.mt5
        df_mod.mt5 = FakeMt5()
        try:
            feed = df_mod.MarketDataFeed()
            feed._connected = True
            feed.fetch_ohlcv(symbol="EURUSD", timeframe="M15", count=5)
            feed.fetch_ohlcv(symbol="EURUSD", timeframe="M15", count=5, include_forming=True)
        finally:
            df_mod.mt5 = original
        self.assertEqual(calls, [1, 0])


# --------------------------------------------------------------------------- #
# 3. Rischio: mai oltre il rischio massimo
# --------------------------------------------------------------------------- #
class RiskManagerTest(unittest.TestCase):
    def test_lot_below_minimum_means_no_trade(self):
        # 20 EUR all'1% = 0,20 di rischio; con 10 pip di stop servirebbero 0,002 lotti
        rm = RiskManager(account_balance=20, risk_per_trade_pct=1)
        self.assertEqual(rm.calculate_lot_size(1.1000, 1.0990), 0.0)

    def test_zero_stop_distance_means_no_trade(self):
        rm = RiskManager(account_balance=10_000, risk_per_trade_pct=1)
        self.assertEqual(rm.calculate_lot_size(1.1, 1.1), 0.0)

    def test_normal_case_unchanged(self):
        # 10.000 all'1% = 100; 20 pip di stop -> 0,50 lotti
        rm = RiskManager(account_balance=10_000, risk_per_trade_pct=1)
        self.assertEqual(rm.calculate_lot_size(1.1000, 1.0980), 0.5)

    def test_llm_lot_capped_to_zero_when_risk_too_small(self):
        rm = RiskManager(account_balance=20, risk_per_trade_pct=1)
        self.assertEqual(rm.cap_llm_lot_size(0.5, 1.1000, 1.0990), 0.0)


class ExposureTest(unittest.TestCase):
    def test_currency_exposure_counts_both_legs(self):
        exp = currency_exposure([("EURUSD", "BUY"), ("USDJPY", "BUY")])
        self.assertEqual(exp, {"EUR": 1, "USD": 0, "JPY": -1})

    def test_same_symbol_twice_is_blocked(self):
        ok, reason = check_new_position("EURUSD", "BUY", [("EURUSD", "BUY")], 3, 1)
        self.assertFalse(ok)
        self.assertIn("EURUSD", reason)

    def test_correlated_dollar_bet_is_blocked(self):
        ok, reason = check_new_position("GBPUSD", "BUY", [("EURUSD", "BUY")], 3, 1)
        self.assertFalse(ok)
        self.assertIn("USD", reason)

    def test_hedging_trade_is_allowed(self):
        ok, _ = check_new_position("USDJPY", "BUY", [("EURUSD", "BUY")], 3, 1)
        self.assertTrue(ok)

    def test_max_open_positions(self):
        ok, reason = check_new_position("AUDNZD", "BUY", [("EURUSD", "BUY"), ("USDJPY", "BUY")], 2, 5)
        self.assertFalse(ok)
        self.assertIn("2", reason)

    def test_daily_loss_limit(self):
        # partito da 1.000, ora 970: -3% -> limite del 3% raggiunto
        self.assertTrue(daily_loss_limit_reached(day_pnl=-30, equity=970, limit_pct=3))
        self.assertFalse(daily_loss_limit_reached(day_pnl=-29, equity=971, limit_pct=3))
        self.assertFalse(daily_loss_limit_reached(day_pnl=50, equity=1050, limit_pct=3))


class AccountStateTest(unittest.TestCase):
    def test_without_mt5_uses_configured_balance(self):
        state = read_account_state(None, magic=1, fallback_balance=500)
        self.assertEqual(state, AccountState(equity=500, open_positions=[], day_pnl=0.0))

    def test_reads_equity_positions_and_today_pnl_for_our_magic_only(self):
        class FakeMt5:
            def account_info(self):
                return SimpleNamespace(equity=990.0)

            def positions_get(self):
                return [SimpleNamespace(symbol="EURUSD", type=0, magic=7, profit=-4.0),
                        SimpleNamespace(symbol="GBPUSD", type=1, magic=99, profit=50.0)]

            def history_deals_get(self, start, end):
                return [SimpleNamespace(magic=7, profit=-10.0, commission=-0.7, swap=0.0),
                        SimpleNamespace(magic=99, profit=100.0, commission=0.0, swap=0.0)]

        now = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
        state = read_account_state(FakeMt5(), magic=7, fallback_balance=500, now=now)
        self.assertEqual(state.equity, 990.0)
        self.assertEqual(state.open_positions, [("EURUSD", "BUY")])
        self.assertAlmostEqual(state.day_pnl, -14.7)


# --------------------------------------------------------------------------- #
# 4. Costi nel backtest
# --------------------------------------------------------------------------- #
class CostsTest(unittest.TestCase):
    def test_costs_reduce_r_multiple(self):
        # BUY a 1.1000, stop 1.0990 (10 pip), uscita a TP 1.1020 (+20 pip), costo 1 pip
        res = realized_result("BUY", 1.1000, 1.1020, 1.0990, pip_size=0.0001, cost_pips=1.0)
        self.assertAlmostEqual(res["r_multiple_gross"], 2.0)
        self.assertAlmostEqual(res["r_multiple"], 1.9)
        self.assertAlmostEqual(res["pips"], 19.0)

    def test_costs_make_losses_bigger(self):
        res = realized_result("SELL", 1.1000, 1.1010, 1.1010, pip_size=0.0001, cost_pips=1.0)
        self.assertAlmostEqual(res["r_multiple"], -1.1)

    def test_summary_reports_gross_and_net(self):
        t = dict(timestamp="t", symbol="EURUSD", action="BUY", confidence=60, entry_price=1.1,
                 take_profit=1.102, stop_loss=1.099, lot_size=0.1, outcome="TP", exit_price=1.102,
                 pips=19.0, r_multiple=1.9, reasoning="x", r_multiple_gross=2.0)
        stats = summarize([BacktestTrade(**t), BacktestTrade(**{**t, "outcome": "SL", "r_multiple": -1.1,
                                                                   "r_multiple_gross": -1.0})])
        self.assertAlmostEqual(stats["total_r"], 0.8)
        self.assertAlmostEqual(stats["total_r_gross"], 1.0)


# --------------------------------------------------------------------------- #
# 5. Analisti attivi ed esecuzione al prezzo reale
# --------------------------------------------------------------------------- #
class ActiveAnalystsTest(unittest.TestCase):
    def test_macro_excluded_without_news(self):
        from core.ensemble import MACRO_LABEL, TECHNICAL_LABEL, active_analysts
        analysts = {TECHNICAL_LABEL: ("b1", "p1"), MACRO_LABEL: ("b2", "p2")}
        self.assertEqual(list(active_analysts(analysts, has_news=False)), [TECHNICAL_LABEL])
        self.assertEqual(len(active_analysts(analysts, has_news=True)), 2)


class ExecutorRealPriceTest(unittest.TestCase):
    def test_order_not_sent_when_spread_breaks_risk_reward(self):
        import core.executor as ex

        sent = []

        class FakeMt5:
            ORDER_TYPE_BUY, ORDER_TYPE_SELL, TRADE_ACTION_DEAL = 0, 1, 1
            ORDER_TIME_GTC, ORDER_FILLING_IOC, TRADE_RETCODE_DONE = 0, 1, 10009

            def symbol_info_tick(self, symbol):
                # chiusura candela 1.10000, ma l'ask reale e' 1.10010 (1 pip di spread)
                return SimpleNamespace(ask=1.10010, bid=1.10000)

            def order_send(self, request):
                sent.append(request)
                return SimpleNamespace(retcode=10009, _asdict=lambda: {})

        signal = {"action": "BUY", "confidence_percentage": 60, "lot_size": 0.1,
                  # sulla chiusura: TP +3 pip, SL -2 pip -> R:R 1,5; all'ask: TP +2, SL -3 -> 0,67
                  "take_profit_price": 1.10030, "stop_loss_price": 1.09980, "reasoning": "x"}
        original = ex.mt5
        ex.mt5 = FakeMt5()
        try:
            out = ex.OrderExecutor(dry_run=False).execute("EURUSD", signal)
        finally:
            ex.mt5 = original
        self.assertEqual(out["status"], "skipped")
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
