"""P3.23: gli LLM sono estrattori di caratteristiche (D-002). Schema chiuso, nessuna confidenza
dichiarata; la caratteristica per il modello è x = dir_llm · dir_candidato · forza ∈ [−3, 3]."""
import pytest
from pydantic import ValidationError

from app.extractors import AnalystView, feature_from_result, signed_feature
from domain.types import Direction
from ports import LlmResult

VALID = {"direzione": 1, "forza": 2, "orizzonte": "intraday", "motivazioni": ["EMA20 sopra", "RSI 60"]}


def test_valid_view_parses():
    assert AnalystView.model_validate(VALID).forza == 2


def test_schema_rejects_confidence_field():
    with pytest.raises(ValidationError):
        AnalystView.model_validate({**VALID, "confidenza": 80})


@pytest.mark.parametrize("patch", [
    {"direzione": 2}, {"direzione": "BUY"}, {"forza": 4}, {"forza": -1},
    {"orizzonte": "settimane"}, {"motivazioni": ["a", "b", "c", "d"]}, {"motivazioni": ["x" * 301]},
    {"extra": 1},
])
def test_schema_rejects_extra_and_out_of_range(patch):
    with pytest.raises(ValidationError):
        AnalystView.model_validate({**VALID, **patch})


@pytest.mark.parametrize("dir_llm, cand, forza, expected", [
    (1, Direction.BUY, 3, 3.0), (1, Direction.SELL, 3, -3.0),
    (-1, Direction.SELL, 2, 2.0), (-1, Direction.BUY, 2, -2.0),
    (0, Direction.BUY, 3, 0.0), (1, Direction.BUY, 0, 0.0),
])
def test_signed_feature_table(dir_llm, cand, forza, expected):
    view = AnalystView.model_validate({**VALID, "direzione": dir_llm, "forza": forza})
    assert signed_feature(view, cand) == expected


def _result(parsed, valid):
    return LlmResult(parsed, "raw", "m", "d", "v1", 1.0, 1, 1, 1, valid, "" if valid else "schema: x")


def test_invalid_output_gives_missing_feature_and_llm_invalid_flag():
    assert feature_from_result(_result(None, False), Direction.BUY) == (None, True)


def test_valid_output_gives_feature():
    assert feature_from_result(_result(AnalystView.model_validate(VALID), True), Direction.SELL) == (-2.0, False)
