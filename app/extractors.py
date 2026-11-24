"""Analisti LLM come estrattori di caratteristiche (D-002).

Schema chiuso: niente campo di confidenza, niente chiavi in più. La caratteristica che entra
nel modello di probabilità è x = dir_llm · dir_candidato · forza, in [−3, 3]:
positiva se l'analista concorda con il candidato, negativa se lo contraddice.
"""
from typing import Annotated, Literal, Optional, cast

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from domain.types import Direction
from ports import LlmResult


class AnalystView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    direzione: Literal[-1, 0, 1]
    forza: int = Field(ge=0, le=3)
    orizzonte: Literal["intraday", "giorni"]
    motivazioni: list[Annotated[str, StringConstraints(max_length=300)]] = Field(max_length=3)


def signed_feature(view: AnalystView, direction: Direction) -> float:
    dir_cand = 1 if direction is Direction.BUY else -1
    return float(view.direzione * dir_cand * view.forza)


def feature_from_result(result: LlmResult, direction: Direction) -> tuple[Optional[float], bool]:
    """(caratteristica, llm_non_valido). Un output non valido è una caratteristica mancante, mai uno zero:
    lo zero direbbe "analista neutrale", che è un'altra informazione."""
    if not result.schema_valid or result.parsed is None:
        return None, True
    return signed_feature(cast(AnalystView, result.parsed), direction), False  # schema passato: AnalystView
