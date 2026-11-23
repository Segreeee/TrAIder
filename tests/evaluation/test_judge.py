"""P5.07: revisore giudice alla cieca (D-012). Non decide: produce {veto, checks}; il veto può solo togliere."""
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from evaluation.judge import CHECK_IDS, JudgeCase, JudgeVerdict, apply_veto, build_judge_prompt, deterministic_checks

OPINIONS = [["prezzo sotto la media a 20 periodi", "RSI in calo"], ["BCE accomodante, euro debole"]]
CASE = JudgeCase(symbol="EURUSD", direction="SELL", d_sl_pips=20.0, d_tp_pips=30.0, htf_trend="ribassista",
                 indicators={"rsi": 41.2, "momentum": -1.1}, opinions=OPINIONS,
                 news=["BCE lascia i tassi invariati"])


def test_prompt_has_no_role_labels_confidence_or_account():
    system, user = build_judge_prompt(CASE, seed=0)
    text = (system + user).lower()
    for banned in ("tecnico", "macro", "confidenza", "forza", "equity", "capitale", "lotto", "saldo", "rischio %"):
        assert banned not in text, banned
    for opinion in OPINIONS:
        for reason in opinion:
            assert reason.lower() in text  # i pareri ci sono, senza dire di chi sono
    assert all(check in text for check in CHECK_IDS)


def test_order_shuffled_deterministically():
    many = [[f"motivo {i}"] for i in range(6)]
    case = JudgeCase(**{**CASE.__dict__, "opinions": many})
    first = build_judge_prompt(case, seed=7)[1]
    assert first == build_judge_prompt(case, seed=7)[1]
    orders = {tuple(sorted(range(6), key=lambda i: build_judge_prompt(case, seed=s)[1].index(f"motivo {i}")))
              for s in range(10)}
    assert len(orders) > 1  # il seme cambia l'ordine
    assert "Parere 1" in first and "Parere 6" in first


def test_schema_is_closed():
    ok = {"veto": False, "checks": [{"id": CHECK_IDS[0], "passed": True, "evidence": "trend H1 ribassista"}]}
    assert JudgeVerdict.model_validate(ok).veto is False
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate({**ok, "confidenza": 80})
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate({"veto": True, "checks": [{"id": "inventato", "passed": False, "evidence": "x"}]})
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate({"veto": True, "checks": []})


def test_deterministic_checks_are_code():
    (trend,) = [c for c in deterministic_checks(CASE) if c.id == "direzione_coerente"]
    assert trend.passed
    against = JudgeCase(**{**CASE.__dict__, "htf_trend": "rialzista"})
    (trend,) = [c for c in deterministic_checks(against) if c.id == "direzione_coerente"]
    assert not trend.passed and "rialzista" in trend.evidence


@given(st.sampled_from(["TRADE", "HOLD"]), st.booleans())
def test_veto_only_removes(action, veto):
    assert apply_veto(action, veto) in {action, "HOLD"}
    assert apply_veto(action, False) == action
