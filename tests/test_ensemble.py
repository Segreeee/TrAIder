"""Eseguire con: .venv\\Scripts\\python.exe -m unittest discover tests"""
import unittest

from core.ensemble import collect_persona_signals, judge_signal
from core.qwen_brain import QwenBrain, QwenBrainError


def sig(action="BUY"):
    return {"action": action, "confidence_percentage": 70, "lot_size": 0.1,
            "take_profit_price": 1.12, "stop_loss_price": 1.09, "reasoning": "x"}


class FakeBrain:
    def __init__(self, result):
        self.result, self.prompts = result, []

    def get_trade_signal(self, prompt, system_prompt=None):
        self.prompts.append(prompt)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


MARKET = {"indicators": {"last_close": 1.1}, "candles": []}


class EnsembleTest(unittest.TestCase):
    def test_collects_both_analysts(self):
        analysts = {"A": (FakeBrain(sig("BUY")), "p1"), "B": (FakeBrain(sig("SELL")), "p2")}
        out = collect_persona_signals("prompt", analysts)
        self.assertEqual({k: v["action"] for k, v in out.items()}, {"A": "BUY", "B": "SELL"})

    def test_failed_analyst_is_skipped(self):
        analysts = {"A": (FakeBrain(QwenBrainError("ollama giu'")), "p1"), "B": (FakeBrain(sig("HOLD")), "p2")}
        self.assertEqual(list(collect_persona_signals("prompt", analysts)), ["B"])

    def test_all_down_returns_empty_for_fallback(self):
        analysts = {"A": (FakeBrain(QwenBrainError("x")), "p1"), "B": (FakeBrain(QwenBrainError("y")), "p2")}
        self.assertEqual(collect_persona_signals("prompt", analysts), {})

    def test_judge_sees_analyst_verdicts_and_warns_when_one_missing(self):
        judge = FakeBrain(sig("HOLD"))
        both = {"A": sig("BUY"), "B": sig("SELL")}
        judge_signal(judge, both, "EURUSD", MARKET, [], None)
        self.assertIn("BUY", judge.prompts[0])
        self.assertIn("SELL", judge.prompts[0])
        self.assertNotIn("ATTENZIONE", judge.prompts[0])

        judge_signal(judge, {"A": sig("BUY")}, "EURUSD", MARKET, [], None)
        self.assertIn("ATTENZIONE: solo 1 analista su 2", judge.prompts[1])

    def test_think_block_is_stripped_before_json_parse(self):
        raw = '<think>ragiono...\n{"action": "SELL"}</think>\n{"action":"BUY","confidence_percentage":60,' \
              '"lot_size":0.1,"take_profit_price":1.2,"stop_loss_price":1.1,"reasoning":"ok"}'
        self.assertEqual(QwenBrain._parse_and_validate(raw)["action"], "BUY")


if __name__ == "__main__":
    unittest.main()
