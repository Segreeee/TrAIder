"""Lotto offline del revisore giudice (P5.08, D-012, D-018), lanciato a mano perché l'API esterna costa:

    python -m evaluation.judge_batch            (richiede REMOTE_JUDGE_BASE_URL, _MODEL, _API_KEY nel .env)

Per ogni ciclo del campione (20% con seme, REMOTE_JUDGE_SAMPLE_PCT) con un candidato della variante di produzione
senza veto: 3 ripetizioni dello stesso prompt (stabilità), ordine dei pareri invertito (bias di posizione), ruoli
nominati (bias di etichetta). Tutte le chiamate vanno in llm_calls; il veto in ombra è la maggioranza delle
ripetizioni valide. Se nessuna è valida il ciclo resta in coda per il lotto successivo.
"""
import hashlib
import json
import logging
from typing import Optional, cast

from app.config import Settings
from domain.costs import distance_pips
from domain.pip import pip_size
from evaluation.judge import JUDGE_PROMPT_VERSION, JudgeCase, JudgeVerdict, build_judge_prompt
from ports import JudgeInput, Llm, SignalStore, call_validated

log = logging.getLogger(__name__)
REPEATS, SEED = 3, 20261123
TECH = ("momentum", "rsi_dev", "macd_hist_atr")


def in_sample(cycle_id: int, pct: float, seed: int = SEED) -> bool:
    """Campione deterministico: lo stesso ciclo è sempre dentro o sempre fuori, per un dato seme."""
    h = int.from_bytes(hashlib.sha256(f"{seed}:{cycle_id}".encode()).digest()[:8], "big")
    return h % 10_000 < pct * 100


def to_case(item: JudgeInput) -> JudgeCase:
    c, snap = item.record.candidate, json.loads(item.input_json or "{}")
    pip = pip_size(c.symbol)
    return JudgeCase(
        symbol=c.symbol, direction="BUY" if c.direction.value == "BUY" else "SELL",
        d_sl_pips=distance_pips(c.entry, c.sl, pip), d_tp_pips=distance_pips(c.tp, c.entry, pip),
        htf_trend=snap.get("htf_trend", "non disponibile"),
        indicators={k: float(item.record.features[k]) for k in TECH if item.record.features.get(k) is not None},
        opinions=list(item.views.values()), roles=list(item.views),
        news=[n["headline"] for n in snap.get("news", [])])


def run_judge_batch(store: SignalStore, llm: Optional[Llm], cfg: Settings, seed: int = SEED) -> int:
    """Restituisce quanti cicli hanno ricevuto il veto in ombra."""
    if llm is None:
        log.info("giudice esterno non configurato (Q-001): nessuna chiamata")
        return 0
    judged = 0
    for item in store.judge_queue(cfg.production_variant):
        if not in_sample(item.cycle_id, cfg.remote_judge_sample_pct, seed):
            continue
        case, vetoes = to_case(item), []
        # il seme dell'ordine è il cycle_id: riproducibile dall'archivio senza salvarlo a parte
        prompts = [("giudice", build_judge_prompt(case, seed=item.cycle_id))] * REPEATS + [
            ("giudice-inverso", build_judge_prompt(case, seed=item.cycle_id, reverse=True)),
            ("giudice-ruoli", build_judge_prompt(case, seed=item.cycle_id, labeled=True))]
        for role, (system, user) in prompts:
            result = call_validated(llm, system, user, JudgeVerdict, prompt_version=JUDGE_PROMPT_VERSION,
                                    max_retries=cfg.llm_max_retries)
            store.record_llm_call(item.cycle_id, role, result)
            if role == "giudice" and result.schema_valid:
                vetoes.append(cast(JudgeVerdict, result.parsed).veto)
        if vetoes:
            store.set_veto_shadow(item.cycle_id, sum(vetoes) * 2 > len(vetoes))
            judged += 1
    return judged


def main() -> int:  # pragma: no cover - chiama un'API esterna a pagamento
    from adapters.llm_openai import OpenAiLlm, build_client
    from adapters.sqlite_store import SqliteStore
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    cfg = Settings()
    if not (cfg.remote_judge_base_url and cfg.remote_judge_model and cfg.remote_judge_api_key):
        log.error("giudice esterno non configurato: REMOTE_JUDGE_BASE_URL, REMOTE_JUDGE_MODEL, REMOTE_JUDGE_API_KEY")
        return 1
    key = cfg.remote_judge_api_key.get_secret_value()
    client = build_client(base_url=cfg.remote_judge_base_url, api_key=key, timeout_s=cfg.llm_timeout_seconds)
    llm = OpenAiLlm(client, model=cfg.remote_judge_model, model_digest=f"api:{cfg.remote_judge_model}",
                    seed=cfg.llm_seed, secrets=[key])
    store = SqliteStore(cfg.db_path)
    try:
        log.info("cicli giudicati: %d", run_judge_batch(store, llm, cfg))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
