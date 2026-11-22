# PROGRESS
**Stato:** Fase 3 — Implementazione TDD · **Aggiornato:** 2026-11-22 · **Prossima azione:** P3.22 (prossimo passo senza attese). In attesa [UTENTE]: P3.05 (fuso MT5), P3.18 (decisione su Finnhub, vedi T-008), P3.21 (.env).

## Piano
| # | Fase | Obiettivo | Criterio di uscita (verificabile) | Stato |
|---|------|-----------|-----------------------------------|-------|
| 0 | Lettura del contesto | Capire il sistema, creare CLAUDE.md/PROGRESS.md/DECISIONS.md | 30 test verdi; tre documenti presenti | fatto |
| 1 | Alternative (niente codice) | D1–D12 con matrici pesate e raccomandazioni | `docs/ALTERNATIVE.md` + un ADR per decisione; **approvazione utente** | fatto |
| 2 | Piano a fasi | Passi piccoli con test, file, accettazione, rischio | Piano in questo file; **approvazione utente** | fatto |
| 3 | Implementazione TDD | Dominio, porte, adattatori, orchestrazione, archivio | `pytest` verde; copertura dominio ≥ 85% | in corso |
| 4 | Modello di confidenza | p0, p*, EV, logistica walk-forward, gate EV_5 | Test obbligatori della specifica verdi | fatta (dominio); collegamento in P3.26 |
| 5 | Valutazione | Test in avanti su demo; confronto delle 7 varianti | Report con BSS, EV e intervalli | da fare |
| 6 | Dashboard | Segnali, rischio, curve, calibrazione, confronti | Leggibile da telefono; ogni numero dall'archivio | da fare |
| 7 | Revisione e pubblicazione | Review, security scan, README onesto | `/code-review`, `/ecc:python-review`, `/ecc:security-scan` puliti | da fare |

## Dettaglio delle fasi
Piano scritto con l'agente `ecc:planner` (55 passi, uno per commit, in TDD). Comando dei test: `.venv\Scripts\python -m pytest -q`. I passi **[UTENTE]** richiedono un'azione o una conferma dell'utente.

## Formule e convenzioni (allineate alla specifica della Fase 4 dell'utente)
Il planner aveva dedotto le formule da ALTERNATIVE.md; qui sono riscritte sulla specifica originale. Le correzioni rispetto alla sua bozza sono marcate ✎.

1. **Formule** (in pip, misurate dal **prezzo di esecuzione atteso**: ask per BUY, bid per SELL ✎):
   - p0 = d_SL / (d_SL + d_TP); W = (d_TP − c)/d_SL; L = (d_SL + c)/d_SL; p\* = L/(W + L) = (d_SL + c)/(d_SL + d_TP).
   - EV = p·W − (1−p)·L; EV_5 = p_5·W − (1−p_5)·L. Con p = p0, EV = −c/d_SL.
   - p = sigmoid(logit(p0) + Σ β_k·x_k) ✎ con le caratteristiche della specifica, standardizzate: voto del tecnico (−1/0/+1), voto del macro (solo con notizie reali), accordo, allineamento con il trend H1, momentum (chiusura − EMA20)/ATR limitato a ±3, d_SL/ATR, sessione di mercato. La confidenza dichiarata dall'LLM non entra.
   - Pochi dati: Beta(κ·p0 + vinti, κ·(1−p0) + persi), κ = 20; p_5 = quantile al 5% (Beta, o bootstrap per la logistica).
   - ✎ **Kelly sulla p stimata, come da specifica:** f\* = p − (1−p)/(W/L); rischio% = min(RISK_PER_TRADE_PCT, λ·f\*), λ = 0.25; se f\* ≤ 0 non si opera.
   - Gate: si opera solo se EV_5 > EV_MIN (default 0).
   - ✎ **Confidenza mostrata all'utente** = P(p > p\* | dati) dalla distribuzione a posteriori, più p, p\*, EV e intervallo (passo P4.03).
   - ✎ **Attivazione del modello:** β ≠ 0 solo con almeno MIN_TRADES_FOR_MODEL (default 100) candidati risolti **e** Brier skill score > 0 fuori campione (passo P4.04); altrimenti β = 0 e "nessun vantaggio dimostrato". I candidati contano anche se non eseguiti (Q-004).
2. **Il rischio per operazione include il costo:** lotto · (d_SL + c) in pip · valore del pip in EUR ≤ capitale · rischio%. Scelta prudente, più severa della specifica: da confermare.
3. **Simulatore:** barre bid, ingresso alla chiusura più spread per i BUY ✎; c = spread (colonna MT5) + commissione + slippage di configurazione; SL prioritario se TP e SL cadono nella stessa candela; orizzonte di 96 barre.
4. **Generatore baseline:** direzione se chiusura vs EMA20 concorda con il trend H1; SL = 1.0·ATR, TP = 1.5·ATR, quindi p0 ≈ 0.4.
5. **Versioni delle dipendenze:** in P3.01 si fissano con `==` alla versione installata.
6. **scipy** diventa dipendenza diretta (`beta.ppf`, `optimize`).
7. **Logistica con offset logit(p0)** fatta con scipy.optimize, non con sklearn, così la proprietà "β = 0 ⇒ p = p0" vale esattamente. sklearn resta per le metriche. La dashboard usa `string.Template` della stdlib.

## Blocco 0 — Prerequisiti di sicurezza e ambiente (Fase 3)

### P3.01 — Ambiente di sviluppo e guardie dei test
- **Obiettivo:** rendere pytest, hypothesis, coverage, pydantic-settings e scikit-learn installabili e fissati; i test devono essere deterministici e senza rete.
- **Test prima:**
  - `tests/test_guardrails.py::test_network_is_blocked`: `socket.create_connection(("example.com", 80))` solleva un errore, grazie a una fixture autouse in `tests/conftest.py`.
  - `test_hypothesis_profile_is_deterministic`: il profilo attivo ha `derandomize=True` e `deadline=None`.
  - `test_metatrader5_not_imported_by_tests`: `"MetaTrader5" not in sys.modules` a fine sessione.
- **File:**
  - creati: `requirements-dev.txt` (pytest, hypothesis, coverage, pydantic-settings, scikit-learn con `==`), `tests/conftest.py`, `pytest.ini` (`testpaths = tests`), `tests/test_guardrails.py`;
  - modificati: `.gitignore` (`.hypothesis/`, `.coverage`, `data/`), `requirements.txt` (scipy, pydantic-settings fissati).
- **Accettazione:**
  - `.venv\Scripts\python -m pip install -r requirements-dev.txt`
  - `.venv\Scripts\python -m pytest -q` → 33 passed (30 vecchi + 3 nuovi).
- **Rischio:** basso. L'unico punto delicato è che la guardia di rete non rompa i test esistenti: usano solo fake.
- **Dipendenze:** nessuna. L'installazione usa la rete, ma è un comando di setup, non un test.

### P3.02 — Doppio consenso nell'executor attuale (T-006)
- **Obiettivo:** chiudere subito la falla: oggi basta `dry_run=False` per arrivare a `order_send`.
- **Test prima** (in `tests/test_live_consent.py`, con un FakeMt5 che registra `order_send`):
  - `test_dry_run_false_alone_sends_no_order`;
  - `test_allow_live_alone_sends_no_order`;
  - `test_both_flags_required_to_reach_order_send`;
  - hypothesis `test_order_send_called_iff_double_consent`: `@given(booleans(), booleans())`, `order_send` è chiamato ⇔ `not dry_run and allow_live`;
  - `test_settings_allow_live_trading_defaults_false`.
- **File:**
  - modificati: `core/executor.py` (`OrderExecutor(dry_run, allow_live_trading=False)`; altrimenti solo simulato), `config/settings.py` (`allow_live_trading`, default False), `main.py` (passa il flag), `.env.example` (`ALLOW_LIVE_TRADING=false`);
  - creato: `tests/test_live_consent.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/test_live_consent.py tests/test_risk_news_costs.py -q`
- **Rischio:** medio, perché è il percorso dei soldi.
  - Il test esistente `ExecutorRealPriceTest` usa `dry_run=False`: va adattato aggiungendo il secondo flag nel costruttore. L'asserzione resta identica: va segnalato nel commit.
  - Le regole deny potrebbero bloccare le modifiche a `.env.example` o i comandi che contengono la stringa del flag. In quel caso ci si ferma e si chiede a te, senza aggirarle. Nei test i nomi restano in minuscolo (`allow_live`).
- **Dipendenze:** P3.01.

### P3.03 — Controllo della direzione di TP/SL (T-004)
- **Obiettivo:** il gate R:R non deve più accettare livelli invertiti.
- **Test prima** (in `tests/test_tp_sl_direction.py`):
  - `test_buy_with_tp_below_entry_rejected`;
  - `test_sell_with_tp_above_entry_rejected`;
  - `test_valid_buy_and_sell_still_pass`;
  - hypothesis `test_rr_gate_never_accepts_inverted_levels`: per ogni entry, TP e SL generati, se BUY con TP ≤ entry o SL ≥ entry (e simmetrico per SELL), allora il gate restituisce False.
- **File:**
  - modificati: `core/risk_manager.py` (aggiunge `levels_consistent(action, entry, tp, sl)`; `meets_min_risk_reward` riceve `action`), con aggiornamento dei chiamanti in `main.py`, `core/executor.py`, `core/backtester.py`, `dashboard.py`;
  - creato: `tests/test_tp_sl_direction.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest -q` (tutto verde).
- **Rischio:** medio. Cambia la firma usata da 4 chiamanti: prima di modificare, controllare tutti i punti con grep.
- **Dipendenze:** P3.01.

### P3.04 — Diagnosi del fuso orario MT5, senza rete (T-007)
- **Obiettivo:** una funzione pura che stima lo scarto server-UTC, più uno script di sola lettura.
- **Test prima** (in `tests/domain/test_clock.py`):
  - `test_offset_zero_plus2_plus3`: barra in formazione con `time` = epoch del server, `utc_now` noto, M15 → 0, +2, +3 ore;
  - `test_offset_negative`;
  - `test_returns_none_when_bar_too_old` (mercato chiuso, weekend);
  - hypothesis `test_roundtrip_to_utc`: `to_utc(epoch_server, offset)` = istante originale per ogni offset tra −12 e +14 ore.
- **File:**
  - creati: `domain/__init__.py`, `domain/clock.py` (`server_offset_hours(bar_open_epoch, utc_now, tf_minutes)`, `to_utc`), `tools/diagnose_mt5_tz.py` (usa solo `initialize`, `copy_rates_from_pos(pos=0)`, `symbol_info_tick`, `shutdown`; stampa l'offset; nessun ordine), `tests/domain/test_clock.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain/test_clock.py -q`
- **Rischio:** basso. Lo script non è testato con MT5 vero, per scelta.
- **Dipendenze:** P3.01.

### P3.05 — [UTENTE] Verifica reale del fuso sul terminale
- **Obiettivo:** misurare l'offset reale del server Pepperstone e registrarlo.
- **Azione:**
  1. Tu lanci `.venv\Scripts\python tools\diagnose_mt5_tz.py` con il terminale aperto, a mercato aperto e in un giorno feriale.
  2. Claude registra il risultato in DECISIONS.md: chiude T-007 e annota se i 21 trade storici sono stati risolti con un orario sfasato.
- **Accettazione:** voce in DECISIONS.md con offset e data; T-007 → fatto.
- **Rischio:** basso. Va però ripetuto dopo il cambio dell'ora legale: per questo P3.15 ricalcola l'offset a ogni ciclo.
- **Dipendenze:** P3.04.

---

## Blocco 1 — Dominio puro (Fase 3 + modello della Fase 4)

### P3.06 — Tipi di dominio
- **Obiettivo:** creare `Direction`, `Candidate`, `Decision` e `HoldReason`, con la geometria validata nel costruttore.
- **Test prima** (in `tests/domain/test_types.py`):
  - `test_candidate_rejects_inverted_geometry` (riusa `levels_consistent`, spostata qui da `core/risk_manager.py` con un re-export temporaneo);
  - `test_candidate_rejects_naive_datetime`;
  - `test_hold_reason_values_closed_set` (NO_CANDIDATE, GATE_EV, SAME_SYMBOL, EXPOSURE, MAX_POSITIONS, DAILY_LOSS, LOT_BELOW_MIN, LLM_INVALID);
  - hypothesis `test_valid_candidate_has_positive_distances`.
- **File:** creati `domain/types.py`, `tests/domain/test_types.py`; modificato `core/risk_manager.py` (re-export).
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain/test_types.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.03, P3.04.

### P3.07 — Valore del pip per coppia, conto in EUR
- **Obiettivo:** eliminare i 10 USD fissi.
  - `pip_size(symbol)`;
  - `conversion_symbol(symbol)`: quale coppia EURxxx interrogare, per esempio USDJPY → EURJPY;
  - `pip_value_eur(symbol, eur_quote_rate, lots=1)` = pip_size · 100000 · lots / eur_quote_rate.
- **Test prima** (in `tests/domain/test_pip.py`):
  - obbligatori: `test_eurusd_eur_account` (EURUSD 1.10 → 9.0909 EUR), `test_usdjpy_eur_account` (EURJPY 165 → 1000/165 = 6.0606 EUR), `test_eurgbp_eur_account` (EURGBP 0.85 → 11.7647 EUR);
  - `test_quote_eur_rate_is_one`;
  - `test_symbol_suffix_ignored` ("EURUSD.a");
  - `test_nonpositive_rate_raises`;
  - `test_conversion_symbol` (GBPUSD→EURUSD, USDJPY→EURJPY, AUDCAD→EURCAD, EURGBP→EURGBP);
  - hypothesis `test_pip_value_linear_in_lots`.
- **File:** creati `domain/pip.py`, `tests/domain/test_pip.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain/test_pip.py -q`
- **Rischio:** medio. Un errore di inversione del cambio sbaglierebbe tutti i lotti: i tre casi numerici obbligatori lo coprono.
- **Dipendenze:** P3.06.

### P3.08 — Costi, R lordo/netto e simulatore di esito
- **Obiettivo:**
  - `cost_price(spread_points, point, commission_eur_per_lot, pip_value_eur, slippage_pips, pip_size)`;
  - `realized_result` e `simulate_outcome` spostati in `domain/outcome.py`, puri, su DataFrame.
- **Test prima** (in `tests/domain/test_costs.py` e `tests/domain/test_outcome.py`):
  - casi noti di costo;
  - hypothesis `cost >= spread >= 0`;
  - `test_sl_wins_when_ambiguous`;
  - `test_timeout_uses_last_close`;
  - hypothesis `test_r_net_equals_r_gross_minus_cost_over_dsl`;
  - hypothesis `test_tp_outcome_gross_r_equals_dtp_over_dsl`;
  - i 3 `CostsTest` attuali copiati con le stesse asserzioni contro il nuovo modulo.
- **File:**
  - creati: `domain/costs.py`, `domain/outcome.py` e i due test;
  - modificato: `core/backtester.py` (importa da `domain.outcome`, re-export).
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain -q`
- **Rischio:** basso.
- **Dipendenze:** P3.07.

### P3.09 — Rischio: lotto 0 oppure ≥ minimo, mai oltre il limite
- **Obiettivo:** `lot_size(equity, risk_pct, d_sl, cost, pip_size, pip_value_eur, min_lot, lot_step, max_lot)`, con il costo incluso nel rischio.
- **Test prima** (in `tests/domain/test_risk.py`):
  - `test_lot_below_minimum_means_no_trade`;
  - `test_zero_stop_means_no_trade`;
  - `test_eurusd_normal_case`: 10 000 EUR all'1%, 20 pip, pip a 9.09 EUR, c = 0 → 0.55;
  - hypothesis `test_lot_zero_or_at_least_min`;
  - hypothesis `test_risk_never_exceeds_limit`: lotto·(d_SL+c)/pip·valore ≤ capitale·rischio% + ε;
  - hypothesis `test_lot_is_multiple_of_step_and_le_max`;
  - `test_invalid_inputs_raise` (rischio ≤ 0 o > 100, capitale ≤ 0).
- **File:** creati `domain/risk.py`, `tests/domain/test_risk.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain/test_risk.py -q`
- **Rischio:** medio. Arrotondamenti float vicino al bordo: si arrotonda sempre per difetto con `round(x/step, 9)` come oggi.
- **Dipendenze:** P3.07, P3.08.

### P3.10 — Esposizione
- **Obiettivo:** spostare `split_symbol`, `currency_exposure`, `check_new_position` e `daily_loss_limit_reached` in `domain/exposure.py`. `core/exposure.py` diventa un re-export di una riga, così i vecchi test restano intatti.
- **Test prima** (in `tests/domain/test_exposure.py`):
  - i 6 `ExposureTest` copiati;
  - hypothesis `test_never_two_positions_same_symbol`;
  - hypothesis `test_accepted_position_keeps_every_currency_within_limit`: partendo da uno stato entro i limiti, se accettata, ogni |esposizione| ≤ massimo;
  - hypothesis `test_never_more_than_max_open`.
- **File:** creati `domain/exposure.py` e il test; modificato `core/exposure.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain/test_exposure.py tests/test_risk_news_costs.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.06.

### P4.01 — p0, W, L, p\*, EV
- **Obiettivo:** primo pezzo del modello della Fase 4, in `domain/probability.py`.
- **Test prima** (in `tests/domain/test_probability.py`):
  - `test_p0_known` (d_SL 10, d_TP 15 → 0.4);
  - `test_p_star_known` (c = 1 → 11/25 = 0.44);
  - `test_ev_known` (EV(p0) = −0.1);
  - hypothesis `test_ev_at_p0_equals_minus_c_over_dsl` (qualunque geometria con c < d_TP);
  - hypothesis `test_p0_decreases_when_dtp_increases`;
  - hypothesis `test_ev_zero_at_p_star`;
  - hypothesis `test_ev_increasing_in_p`.
- **File:** creati `domain/probability.py` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain/test_probability.py -q`
- **Rischio:** basso, purché le formule siano confermate (assunzione 1).
- **Dipendenze:** P3.08.

### P4.02 — Beta con κ, p5, EV_5
- **Obiettivo:** `beta_posterior(p0, kappa, wins, losses)`, `p_mean`, `p_quantile(q)` con `scipy.stats.beta.ppf`, ed `ev5`.
- **Test prima:**
  - `test_no_data_mean_is_p0`;
  - hypothesis `test_p5_le_mean`;
  - `test_more_data_narrows_interval`;
  - `test_synthetic_recovers_known_p`: p vera 0.45, n = 3000, Bernoulli con `numpy.random.default_rng(7)`, |media − 0.45| < 0.02;
  - hypothesis `test_ev5_le_ev_mean`.
- **File:** modificati `domain/probability.py` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain/test_probability.py -q`
- **Rischio:** basso.
- **Dipendenze:** P4.01.

### P4.03 — Kelly frazionario e gate EV_5
- **Obiettivo:** `kelly_risk_pct(p, W, L, lam=0.25, cap)` e `ev_gate(ev5, ev_min) -> (bool, HoldReason|None)`.
- **Test prima:**
  - `test_kelly_known_case`;
  - `test_kelly_zero_when_p_le_p_star`;
  - hypothesis `test_kelly_risk_never_exceeds_cap`;
  - hypothesis `test_gate_never_opens_when_ev5_le_ev_min`;
  - `test_beta_zero_never_opens_with_costs` (documenta Q-004: con p = p0 e c > 0 il gate resta chiuso).
- **File:** modificati `domain/probability.py` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/domain/test_probability.py -q`
- **Rischio:** basso.
- **Dipendenze:** P4.02, P3.06.

### P4.04 — Logistica L2 con offset, walk-forward, copertura del dominio
- **Obiettivo:**
  - `fit_offset_logistic(X, y, offset, l2)` con `scipy.optimize.minimize` e `predict`;
  - `walk_forward_fit(rows, t)` usa solo le righe risolte prima di t;
  - `choose_model(n_resolved)`: Beta sotto i 100 candidati, logistica da 100 in su.
- **Test prima** (in `tests/domain/test_logistic.py`):
  - hypothesis `test_beta_zero_gives_p0_exactly`;
  - hypothesis `test_p_in_open_interval`;
  - hypothesis `test_monotone_in_feature_with_positive_beta`;
  - `test_synthetic_recovers_beta`: β veri [0.8, −0.5], n = 5000, seme fisso → |β̂ − β| < 0.15 ed errore di calibrazione per decili < 0.05;
  - `test_walk_forward_ignores_future_rows`: righe successive a t non cambiano il fit;
  - `test_choose_model_threshold_100`.
- **File:** creati `domain/logistic.py`, `tests/domain/test_logistic.py`, `.coveragerc` (`source = domain`, `fail_under = 85`).
- **Accettazione:**
  - `.venv\Scripts\python -m coverage run -m pytest tests/domain -q`
  - `.venv\Scripts\python -m coverage report` (exit 0, ≥ 85%).
- **Rischio:** medio. Convergenza dell'ottimizzatore e tolleranze statistiche: semi fissi, n ampio, tolleranze dichiarate.
- **Dipendenze:** P4.01–P4.03.

---

## Blocco 2 — Porte e adattatori finti (Fase 3)

### P3.11 — Porte MarketData e NewsFeed, fake, contratti, regola anti-futuro
- **Obiettivo:** `ports.py` con i 5 `Protocol` e i DTO (`NewsItem` con `published_at` e `fetched_at` tz-aware), più `domain/news.py::visible_news(items, candle_close)`.
- **Test prima:**
  - `tests/contracts/market_data_contract.py`, funzione riusabile `check_market_data(adapter)`:
    - timestamp UTC tz-aware e crescenti;
    - colonne `open/high/low/close/volume/spread`;
    - ultima chiusura ≤ adesso (solo candele chiuse).
  - `news_contract.py`: ogni notizia ha entrambi i timestamp tz-aware.
  - hypothesis `test_visible_news_never_passes_fetched_after_close`.
  - I contratti girano su `FakeMarketData` e `FakeNews`.
- **File:** creati `ports.py`, `domain/news.py`, `tests/fakes.py`, `tests/contracts/__init__.py`, `tests/contracts/market_data_contract.py`, `tests/contracts/news_contract.py`, `tests/test_contracts_fakes.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/test_contracts_fakes.py tests/domain/test_news.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.06.

### P3.12 — Porta LLM: output validato, temperatura 0, retry limitati
- **Obiettivo:** `ports.call_validated(llm, prompt, schema, max_retries)` restituisce un `LlmResult(parsed, raw, model, model_digest, prompt_version, latency_ms, tokens_in, tokens_out, attempts, schema_valid)`.
- **Test prima** (`tests/contracts/llm_contract.py` su `FakeLlm` con risposte scriptate):
  - `test_valid_output_parsed`;
  - `test_invalid_then_valid_retries_once`;
  - `test_gives_up_after_max_retries` (tentativi = max_retries + 1, `schema_valid=False`, nessuna eccezione non gestita);
  - `test_temperature_zero_requested`;
  - `test_result_carries_model_digest_and_prompt_version`.
- **File:** modificati `ports.py`, `tests/fakes.py`; creato `tests/contracts/llm_contract.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/test_contracts_fakes.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.11.

### P3.13 — Porta Broker, broker simulato, doppio consenso nella porta
- **Obiettivo:**
  - `adapters/sim_broker.py`: fill al tick più spread, posizioni in memoria, mai MetaTrader5;
  - `ports.build_broker(dry_run, allow_live, make_mt5_broker)`: restituisce il broker MT5 solo con `dry_run=False` e `allow_live=True`.
- **Test prima:**
  - hypothesis `test_mt5_factory_called_iff_double_consent`;
  - `broker_contract.py`:
    - `submit` con lotto 0 → rifiutato;
    - `submit` restituisce `mode`, `fill_price`, `spread`;
    - `positions()` riflette i submit.
  - `test_sim_broker_never_imports_metatrader5`.
- **File:** creati `adapters/__init__.py`, `adapters/sim_broker.py`, `tests/contracts/broker_contract.py`; modificati `ports.py` e `tests/test_contracts_fakes.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/test_contracts_fakes.py -q`
- **Rischio:** medio, perché è il punto di sicurezza principale. Lo coprono la proprietà su tutte le combinazioni e la difesa ripetuta in P3.16.
- **Dipendenze:** P3.11, P3.02.

### P3.14 — Porta SignalStore, fake e contratto
- **Obiettivo:** definire i metodi `begin_cycle`, `record_llm_call`, `record_candidate`, `record_execution`, `record_outcome`, `pending_candidates`, `last_cycle`, con un `FakeStore` a liste.
- **Test prima** (`store_contract.py`):
  - `test_begin_cycle_idempotent` (stessa coppia simbolo/candela → None alla seconda);
  - `test_outcome_recorded_once`;
  - `test_candidate_unique_per_variant`;
  - `test_pending_excludes_resolved`.
- **File:** modificati `ports.py`, `tests/fakes.py`; creato `tests/contracts/store_contract.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/test_contracts_fakes.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.11.

---

## Blocco 3 — Adattatori reali (Fase 3)

### P3.15 — Dati MT5
- **Obiettivo:** `adapters/mt5_data.py`, con il modulo `mt5` iniettato nel costruttore (niente più sostituzione di variabili di modulo).
  - Solo candele chiuse (`start_pos=1`).
  - Orari convertiti in UTC con `domain/clock.py`, offset ricalcolato a ogni ciclo.
  - Colonna `spread` conservata.
  - `eur_quote_rate(symbol)` per il valore del pip.
- **Test prima** (FakeMt5):
  - `check_market_data` dal contratto;
  - `test_fetch_skips_forming_candle` (porting di `ClosedCandlesTest`, stessa asserzione `[1, 0]`);
  - `test_timestamps_converted_with_offset`;
  - `test_spread_column_kept`;
  - `test_eur_quote_rate_uses_conversion_symbol`.
- **File:** creati `adapters/mt5_data.py`, `tests/adapters/test_mt5_data.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/adapters/test_mt5_data.py -q`
- **Rischio:** medio. Il cambio dell'ora legale è coperto dal ricalcolo per ciclo, con un log se l'offset cambia.
- **Dipendenze:** P3.11, P3.04, P3.05.

### P3.16 — Broker MT5 (mai ordini nei test)
- **Obiettivo:** `adapters/mt5_broker.py`.
  - Il costruttore solleva un errore se `live_allowed` non è True: difesa in profondità.
  - `submit` ricontrolla direzione e R:R ad ask/bid.
  - Usa `magic` e legge commissione e swap dai deal.
  - `account()` restituisce capitale, posizioni del bot e P&L del giorno (porting di `read_account_state`).
- **Test prima:**
  - `broker_contract` con FakeMt5;
  - `test_constructor_refuses_without_live_allowed`;
  - `test_order_not_sent_when_spread_breaks_risk_reward` (porting, stessa asserzione: `sent == []`);
  - `test_inverted_levels_never_sent`;
  - i 2 `AccountStateTest` portati.
- **File:** creati `adapters/mt5_broker.py`, `tests/adapters/test_mt5_broker.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/adapters/test_mt5_broker.py -q`
- **Rischio:** alto: è l'unico file con `order_send`. Nei test usa sempre FakeMt5 iniettato; resta valido il test di P3.01 che verifica che MetaTrader5 non venga mai importato.
- **Dipendenze:** P3.13, P3.15.

### P3.17 — LLM tramite client OpenAI-compatibile, indipendente dal fornitore
- **Obiettivo:** `adapters/llm_openai.py`, con client `OpenAI` iniettato.
  - Temperatura 0, `seed`, `response_format=json`, rimozione di `<think>`.
  - Usage e latenza registrati.
  - `model_digest` letto con un getter HTTP iniettato (Ollama `/api/show`) oppure dalla versione esplicita del modello remoto.
  - Nessun URL remoto predefinito.
- **Test prima:**
  - `llm_contract` sul client finto;
  - `test_think_block_stripped` (porting da `test_ensemble`);
  - `test_temperature_zero_and_seed_sent`;
  - `test_no_default_remote_base_url`;
  - `test_api_key_not_in_error_messages`.
- **File:** creati `adapters/llm_openai.py`, `tests/adapters/test_llm_openai.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/adapters/test_llm_openai.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.12.

### P3.18 — [UTENTE] Notizie Finnhub (prerequisito T-008)
- **Prerequisito:** Claude riconferma termini e limiti sulle pagine ufficiali di Finnhub e te li riporta. **Tu confermi** prima che si scriva l'adattatore. Se i termini non sono compatibili, il passo si salta e la variante "solo macro" risulta non disponibile.
- **Obiettivo:** `adapters/finnhub_news.py`.
  - urllib della stdlib con opener e orologio iniettati.
  - `published_at` preso dal campo `datetime` UNIX, convertito in UTC; `fetched_at` = orologio.
  - Errore di rete → lista vuota.
  - Chiave come `SecretStr`, mai nei log.
- **Test prima:**
  - `news_contract`;
  - `test_maps_unix_datetime_to_utc`;
  - `test_fetched_at_from_clock`;
  - `test_network_error_returns_empty`;
  - `test_key_redacted_in_logs` (con `caplog`).
- **File:** creati `adapters/finnhub_news.py`, `tests/adapters/test_finnhub_news.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/adapters/test_finnhub_news.py -q`
- **Rischio:** medio, per la licenza: il testo delle notizie resta solo in `data/`.
- **Dipendenze:** P3.11.

### P3.19 — Archivio SQLite: schema D7
- **Obiettivo:** `adapters/schema.sql` con le tabelle `cycles`, `llm_calls`, `candidates`, `executions`, `outcomes` e le colonne di D7.
  - Vincoli: `UNIQUE(symbol, candle_close_utc)`, `UNIQUE(cycle_id, variant)`, FK attive, CHECK su `direction`, `resolution`, `mode`.
  - `adapters/sqlite_store.py` implementa la porta.
- **Test prima:**
  - `store_contract` su `SqliteStore(":memory:")`;
  - `test_foreign_keys_enforced`;
  - `test_check_constraints_reject_bad_values`.
- **File:** creati `adapters/schema.sql`, `adapters/sqlite_store.py`, `tests/adapters/test_sqlite_store.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/adapters/test_sqlite_store.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.14, P3.01 (`data/` ignorata da git).

### P3.20 — Archivio: WAL e sola aggiunta
- **Obiettivo:**
  - `PRAGMA journal_mode=WAL` sul file;
  - trigger che vietano UPDATE e DELETE su `cycles`, `llm_calls` e `candidates`, tranne `veto_shadow` da NULL a un valore;
  - `outcomes` scrivibile una sola volta.
- **Test prima:**
  - `test_wal_enabled_on_file_db` (`tmp_path`);
  - `test_update_cycle_rejected`;
  - `test_delete_candidate_rejected`;
  - `test_veto_shadow_set_once_only`.
- **File:** modificati `adapters/schema.sql` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/adapters/test_sqlite_store.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.19.

---

## Blocco 4 — Orchestrazione (Fase 3)

### P3.21 — [UTENTE] Configurazione con pydantic-settings (D11)
- **Obiettivo:** `app/config.py`, con un'istanza passata come argomento e nessuna lettura all'import.
  - `SecretStr` per chiavi e password.
  - Intervalli validati, per esempio rischio in (0, 5].
  - Validatori incrociati: `DRY_RUN=false` senza il secondo flag → errore all'avvio; `NEWS_PROVIDER=mock` fuori da DRY_RUN → errore; provider sconosciuto → errore.
  - `config_hash` calcolato senza segreti.
  - Variabili del giudice remoto senza default (Q-001).
- **Test prima** (con `Settings(_env_file=None, ...)`):
  - `test_defaults_are_safe`;
  - `test_live_without_second_flag_fails`;
  - `test_mock_news_live_fails` e `test_unknown_provider_fails` (sostituiscono 2 dei `NewsFeedTest`);
  - `test_repr_hides_secrets`;
  - `test_config_hash_excludes_secrets_and_is_stable`;
  - `test_risk_pct_out_of_range_fails`.
- **File:** creati `app/__init__.py`, `app/config.py`, `tests/app/test_config.py`; modificato `.env.example`.
- **Azione utente:** aggiornare il tuo `.env` con i nuovi nomi, per esempio le variabili `QWEN_*` diventano quelle del giudice remoto. Claude non può modificare `.env`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_config.py -q`
- **Rischio:** medio. Se il `.env` non viene aggiornato, la validazione fallisce all'avvio, ed è il comportamento voluto.
- **Dipendenze:** P3.02.

### P3.22 — Indicatori e generatore di candidati baseline
- **Obiettivo:**
  - `app/features.py`: `add_indicators` spostata qui e caratteristiche tecniche con segno (3 al massimo);
  - `app/candidates.py::generate(bars, htf, cfg)`: direzione più SL e TP come multipli di ATR.
- **Test prima:**
  - `test_known_bars_give_expected_candidate`;
  - `test_no_candidate_when_atr_nan`;
  - hypothesis `test_generated_geometry_valid`;
  - `test_no_lookahead`: aggiungere barre future non cambia il candidato della stessa chiusura.
- **File:** creati `app/features.py`, `app/candidates.py`, `tests/app/test_candidates.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_candidates.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.06, P3.21.

### P3.23 — Estrattori LLM con schema chiuso (D2)
- **Obiettivo:** schemi pydantic `TechnicalView` e `MacroView` = `{direzione ∈ {−1, 0, 1}, forza 0..3, orizzonte (Literal), motivazioni (massimo 3)}` con `extra="forbid"`, più la caratteristica `x = dir_llm · dir_cand · forza`.
- **Test prima:**
  - `test_schema_rejects_confidence_field`;
  - `test_schema_rejects_extra_and_out_of_range`;
  - `test_signed_feature_table`;
  - `test_invalid_output_gives_missing_feature_and_llm_invalid_flag`.
- **File:** creati `app/extractors.py`, `tests/app/test_extractors.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_extractors.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.12.

### P3.24 — Prompt separati per tecnico e macro (D4)
- **Obiettivo:** `app/prompts.py` con `build_technical_prompt` (prezzi, indicatori, trend H1; niente notizie) e `build_macro_prompt` (solo notizie con `fetched_at`; niente prezzi). `PROMPT_VERSION` = hash del template.
- **Test prima:**
  - `test_macro_prompt_has_no_prices`: nessun valore OHLC della fixture e nessun numero `\d\.\d{4,}`;
  - `test_technical_prompt_has_no_headlines`;
  - `test_no_account_or_confidence_in_prompts`;
  - `test_prompt_version_changes_with_template`.
- **File:** creati `app/prompts.py`, `tests/app/test_prompts.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_prompts.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.23.

### P3.25 — run_once, parte 1: flusso e idempotenza
- **Obiettivo:** `app/run_once.py`: dati → candidato → LLM → archivio, su porte finte. È la Facade di D-001.
- **Test prima:**
  - `test_second_call_same_candle_does_nothing` (nessuna chiamata LLM, nessuna riga nuova);
  - `test_no_candidate_records_cycle_with_NO_CANDIDATE`;
  - `test_llm_called_only_with_candidate`;
  - `test_macro_only_with_visible_news` (porting di `ActiveAnalystsTest`);
  - `test_llm_down_records_cycle_with_missing_features` (sostituisce i test "analista fallito / tutti giù").
- **File:** creati `app/run_once.py`, `tests/app/test_run_once.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_run_once.py -q`
- **Rischio:** medio: è il cuore del flusso. Va tenuto sotto le 50 righe, con funzioni di passo separate.
- **Dipendenze:** P3.11–P3.14, P3.22–P3.24.

### P3.26 — run_once, parte 2: varianti e decisione
- **Obiettivo:**
  - `app/variants.py`: dizionario nome → funzione(candidato, caratteristiche, statistiche) → p, per le varianti 1, 2, 3, 4, 5 e 7. La 6 è in P5.04.
  - Decisione sulla variante di produzione: gate EV_5, poi Kelly, lotto, esposizione e limite giornaliero, poi broker tramite la porta.
- **Test prima:**
  - `test_all_variants_share_same_candidate`;
  - `test_gate_closed_submits_nothing` (Q-004);
  - `test_daily_loss_stops_before_llm`;
  - `test_exposure_blocks_with_reason`;
  - `test_lot_zero_gives_LOT_BELOW_MIN`;
  - `test_default_broker_is_sim`;
  - hypothesis `test_final_lot_respects_risk_limit`.
- **File:** creato `app/variants.py`; modificati `app/run_once.py` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app -q`
- **Rischio:** medio.
- **Dipendenze:** P3.25, P4.03, P4.04, P3.09, P3.10.

### P3.27 — Risoluzione virtuale di tutti i candidati (Q-004)
- **Obiettivo:** `app/resolve.py::resolve_pending(store, market, now)` risolve ogni candidato, eseguito o no, con le barre successive alla chiusura (TP, SL o TIMEOUT a 96 barre) e scrive `resolved_by='virtuale'`.
- **Test prima:**
  - `test_resolves_non_executed_candidates`;
  - `test_never_uses_bars_up_to_close`;
  - `test_idempotent`;
  - `test_waits_when_not_enough_bars`;
  - `test_r_net_uses_recorded_cost`.
- **File:** creati `app/resolve.py`, `tests/app/test_resolve.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_resolve.py -q`
- **Rischio:** medio: il bias del simulatore (vedi rischi).
- **Dipendenze:** P3.08, P3.25.

### P3.28 — Scheduler allineato alla candela e radice di composizione (D10)
- **Obiettivo:**
  - `app/scheduler.py::next_run(now, tf_min, delay_s)`, funzione pura;
  - ciclo con orologio e sleep iniettati: un ciclo che supera 12 minuti fa saltare il successivo, che viene registrato;
  - al riavvio si elabora solo l'ultima candela chiusa, se ha meno di 5 minuti;
  - `main.py` riscritto come radice di composizione (`--once`).
- **Test prima:**
  - hypothesis `test_next_run_after_now_aligned_and_bounded`;
  - `test_loop_runs_once_per_candle_with_fake_clock`;
  - `test_overrun_skips_and_logs`;
  - `test_recovery_only_recent_candle`;
  - `test_default_composition_uses_sim_broker_and_null_news`.
- **File:** creati `app/scheduler.py`, `tests/app/test_scheduler.py`; modificato `main.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_scheduler.py -q`
- **Rischio:** medio.
- **Dipendenze:** P3.21, P3.25–P3.27.

### P3.29 — [UTENTE] Migrazione dei 30 test come regressione
- **Obiettivo:** `tests/regression/test_legacy_guarantees.py` raccoglie le garanzie dei 30 test, puntate sui moduli nuovi, e una tabella di corrispondenza nel docstring.

  | Test attuali | Destinazione |
  |---|---|
  | NewsFeed (4) | config (P3.21) |
  | ClosedCandles | mt5_data |
  | Risk (4) | domain/risk |
  | Exposure (6) | domain/exposure |
  | Account (2) | mt5_broker |
  | Costs (3) | domain/outcome e metriche |
  | ActiveAnalysts | run_once |
  | ExecutorRealPrice | mt5_broker |
  | think-block | llm_openai |
  | Yahoo (3) | restano finché decidi T-002 |

- **Conferme richieste:**
  - (a) `test_normal_case_unchanged` cambia valore atteso (0.50 → 0.55), perché il vecchio test conteneva il bug del pip fisso;
  - (b) si ritirano `test_judge_prompt_does_not_warn...` e `test_judge_sees_analyst_verdicts...`, perché il giudice decisore sparisce (D-012);
  - (c) "analista fallito / tutti giù" cambiano semantica: diventano "caratteristica mancante", non più fallback sul giudice.
- **File:** creato `tests/regression/test_legacy_guarantees.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/regression -q`
- **Rischio:** medio: perdere una garanzia nel porting. La tabella va confrontata riga per riga.
- **Dipendenze:** P3.15–P3.28.

### P3.30 — Rimozione di core/confidence.py e della pipeline duplicata della dashboard
- **Obiettivo:**
  - eliminare `core/confidence.py`;
  - togliere da `dashboard.py` le funzioni `decide`, `decide_ensemble`, `run_multi_asset_analysis` e `pick_best` e il pulsante che avvia LLM e MT5;
  - la dashboard resta in sola lettura fino a P6.03.
- **Test prima:** `test_no_module_imports_confidence` (grep su `*.py` in `tests/test_guardrails.py`) e `test_dashboard_has_no_llm_or_broker_imports`.
- **File:** rimosso `core/confidence.py`; modificati `dashboard.py` e `tests/test_guardrails.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest -q`
- **Rischio:** basso.
- **Dipendenze:** P3.26.

### P3.31 — [UTENTE] Rimozione dei moduli legacy
- **Obiettivo:**
  - rimuovere `core/ensemble.py`, `core/qwen_brain.py`, `core/executor.py`, `core/risk_manager.py`, `core/exposure.py`, `core/data_feed.py`, `core/prompt_builder.py`, `core/account.py`, `config/settings.py`;
  - rimuovere il percorso LLM di `core/backtester.py` e `backtest.py`; il backtest senza LLM arriva in P5.06;
  - rimuovere i test vecchi, già coperti da P3.29. Restano `core/news_feed.py` e i suoi test per T-002.
- **Conferma richiesta:** cancellazione di `backtest.py` e dei vecchi file di test. Restano comunque recuperabili da git.
- **Test prima:** `test_no_imports_from_removed_modules`.
- **File:** rimossi quelli elencati.
- **Accettazione:**
  - `.venv\Scripts\python -m pytest -q`
  - `.venv\Scripts\python main.py --once --help` parte senza errori di import.
- **Rischio:** medio: import residui. Si controlla con grep prima di cancellare.
- **Dipendenze:** P3.29, P3.30.

---

## Blocco 5 — Archivio completo dei segnali (Fase 3)

### P3.32 — Input completo e riproducibilità
- **Obiettivo:** `cycles.input_json` contiene candele, indicatori, trend H1, notizie con entrambi i timestamp, spread e cambio EUR, più `input_hash`, `code_version` (sha di git iniettato) e `config_hash`.
- **Test prima:**
  - `test_replay_from_input_json_gives_same_decision`;
  - `test_input_json_contains_no_secrets`;
  - `test_input_hash_stable`.
- **File:** modificati `app/run_once.py`; creato `tests/app/test_archive_completeness.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_archive_completeness.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.31.

### P3.33 — Completezza di llm_calls e candidates
- **Obiettivo:** ogni chiamata LLM viene registrata, anche se non valida o in errore. Ogni candidato ha p0, p, p5, p\*, EV, EV_5, `gate_passed`, `final_action`, lotto; `hold_reason` è non nullo se non eseguito.
- **Test prima:** hypothesis `test_every_cycle_has_complete_record`, su tutti gli scenari: nessun candidato, gate chiuso, esposizione, limite giornaliero, lotto minimo, LLM non valido, eseguito. Più `test_invalid_llm_output_recorded`.
- **File:** modificati `app/run_once.py` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_archive_completeness.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.32.

### P3.34 — Costi reali di esecuzione e riconciliazione
- **Obiettivo:**
  - `executions` registra spread, slippage (fill − richiesto), commissione e swap, da SimBroker o dai deal MT5;
  - `outcomes` registra gli esiti del broker accanto a quelli virtuali, con lo scarto in R (soglia D8: 0.1 R).
- **Test prima:** `test_sim_execution_records_spread`, `test_mt5_deal_costs_recorded` (FakeMt5), `test_reconciliation_gap_in_r`.
- **File:** modificati `app/run_once.py`, `app/resolve.py`; creato `tests/app/test_executions.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app/test_executions.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.33, P3.16.

Passo opzionale, non incluso nel conteggio: importare in sola lettura i 21 trade di `logs/signals_history.json` come variante `legacy_llm`, senza toccare il file. Da fare solo se vuoi la continuità storica.

---

## Blocco 6 — Valutazione (Fase 5)

### P5.01 — [UTENTE] Preregistrazione
- **Obiettivo:** `docs/PREREGISTRAZIONE.md`, da committare **prima** di raccogliere dati.
  - Metrica primaria: Brier skill score vs p0 ed EV netto, variante 7 contro variante 2.
  - Metriche secondarie.
  - Soglie: 100 candidati per sbloccare β, obiettivo di 300 trade.
  - Bootstrap: B = 2000, seme fisso, IC 95%.
  - Le 7 varianti, le metriche D12 e la regola "nessuna modifica in corsa".
- **Test prima:** `test_preregistration_exists_and_lists_metrics` (il file contiene le chiavi attese).
- **Accettazione:** il test è verde e tu approvi il documento; il commit ne fa da marca temporale.
- **Rischio:** basso.
- **Dipendenze:** P3.34.

### P5.02 — Metriche
- **Obiettivo:** `evaluation/metrics.py` con:
  - Brier, Brier skill score vs p0, log-loss, calibrazione per decili, AUC (sklearn);
  - max drawdown, R lordo e netto, EV previsto vs realizzato.
- **Test prima:**
  - valori noti per ciascuna metrica;
  - hypothesis `brier ∈ [0, 1]`;
  - `test_bss_of_reference_is_zero`;
  - `test_drawdown_monotone_series_zero`.
- **File:** creati `evaluation/__init__.py`, `evaluation/metrics.py`, `tests/evaluation/test_metrics.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/evaluation/test_metrics.py -q`
- **Rischio:** basso.
- **Dipendenze:** P5.01.

### P5.03 — Bootstrap appaiato e raggruppamenti
- **Obiettivo:** `evaluation/bootstrap.py` con IC appaiati e seme fisso, più `session_of(utc)` (Asia, Londra, New York) e raggruppamento per simbolo e sessione.
- **Test prima:**
  - `test_ci_contains_true_mean_synthetic`;
  - `test_identical_variants_diff_ci_is_zero`;
  - hypothesis `test_session_total_partition`;
  - `test_deterministic_with_seed`.
- **File:** creati `evaluation/bootstrap.py` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/evaluation -q`
- **Rischio:** basso.
- **Dipendenze:** P5.02.

### P5.04 — Variante 6 (decisore legacy in ombra) e disponibilità delle varianti 4/5
- **Obiettivo:**
  - variante 6: prompt legacy in sola ombra, con un flag di configurazione disattivato di default per la latenza, che registra `latency_ms`;
  - le varianti 4 e 5 risultano "non disponibili" se non ci sono notizie visibili, mai simulate.
- **Test prima:**
  - `test_variant6_never_submits_orders`;
  - `test_variant6_off_by_default`;
  - `test_macro_variants_marked_unavailable_without_news`.
- **File:** modificati `app/variants.py`, `app/prompts.py`, `app/config.py` e i test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/app -q`
- **Rischio:** medio: la latenza nella finestra M15. Si misura prima di attivarla.
- **Dipendenze:** P3.26.

### P5.05 — Report automatico
- **Obiettivo:** `evaluation/report.py`: dall'archivio produce un markdown con le 7 varianti appaiate, tutte le metriche di P5.02 e P5.03, per simbolo e sessione. Comando: `python -m evaluation.report --db data\traider.db`.
- **Test prima:**
  - `test_report_on_fake_archive_matches_expected_numbers` (archivio generato con p noto);
  - `test_unavailable_variants_reported_as_such`;
  - `test_report_reads_only` (connessione SQLite in sola lettura).
- **File:** creati `evaluation/report.py`, `tests/evaluation/test_report.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/evaluation/test_report.py -q`
- **Rischio:** basso.
- **Dipendenze:** P5.03, P5.04.

### P5.06 — Backtest solo per le varianti senza LLM
- **Obiettivo:** `evaluation/backtest.py`: walk-forward su barre storiche per le varianti 1 e 2, con lo stesso generatore, modello e `simulate_outcome` del live, e lo spread MT5.
- **Test prima:**
  - `test_refuses_llm_variants`;
  - `test_synthetic_bars_known_outcomes`;
  - `test_walk_forward_no_future_fit`.
- **File:** creati `evaluation/backtest.py`, `tests/evaluation/test_backtest.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/evaluation/test_backtest.py -q`
- **[UTENTE]:** l'esecuzione sullo storico reale richiede il terminale MT5 aperto. Si usano solo dati, nessun ordine.
- **Rischio:** basso.
- **Dipendenze:** P5.02, P4.04.

### P5.07 — Revisore giudice: prompt alla cieca e schema
- **Obiettivo:** `evaluation/judge.py`.
  - Schema `{veto: bool, checks: [{id, passed, evidence}]}` con `extra=forbid`.
  - Prompt anonimo: etichette neutre, ordine casuale con seme, niente confidenza né dati del conto.
  - Controlli deterministici equivalenti scritti in codice.
- **Test prima:**
  - `test_prompt_has_no_role_labels_confidence_or_account`;
  - `test_order_shuffled_deterministically`;
  - hypothesis `test_veto_only_removes`: azione finale con veto ∈ {azione finale senza veto, HOLD}.
- **File:** creati `evaluation/judge.py`, `tests/evaluation/test_judge.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/evaluation/test_judge.py -q`
- **Rischio:** basso.
- **Dipendenze:** P3.17, P3.33.

### P5.08 — [UTENTE] Esecutore offline del giudice in lotti
- **Prerequisito:** scegli il modello locale di un'altra famiglia (J3) e lo scarichi tu con `ollama pull`. Il giudice remoto al 20% solo se hai scelto un fornitore (Q-001).
- **Obiettivo:**
  - giudicare i candidati con `veto_shadow IS NULL`;
  - 3 ripetizioni, ordine invertito ed etichette con nome registrati per stabilità e bias;
  - chiamate salvate in `llm_calls` con ruolo `judge`.
- **Test prima** (con FakeLlm):
  - `test_batch_sets_veto_once`;
  - `test_repetitions_and_swapped_order_recorded`;
  - `test_remote_sample_skipped_when_unconfigured`;
  - `test_remote_sample_is_20pct_seeded`.
- **File:** creato `evaluation/judge_batch.py` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/evaluation/test_judge_batch.py -q`
- **Rischio:** basso.
- **Dipendenze:** P5.07, P3.20.

### P5.09 — Metriche del giudice (D12) e regola di promozione
- **Obiettivo:**
  - precisione e lift dei veti con IC, richiamo;
  - ablation (ΔEV e ΔBSS appaiati con IC);
  - stabilità, bias di posizione e di etichetta, kappa J3-J2, AUC delle motivazioni, allucinazioni;
  - `judge_promotion_decision(metrics)` con le soglie di D12.
- **Test prima:**
  - valori su dati sintetici noti;
  - `test_promotion_requires_30_vetoes_and_100_candidates`;
  - `test_kappa_below_04_archives_line`.
- **File:** creati `evaluation/judge_metrics.py` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/evaluation -q`
- **Rischio:** basso.
- **Dipendenze:** P5.03, P5.08.

### P5.10 — [UTENTE] Avvio del test in avanti in DRY_RUN
- **Obiettivo:** tu avvii il demone in DRY_RUN con il broker simulato e configuri l'Utilità di pianificazione come supervisore. Claude fornisce solo le istruzioni.
- **Checkpoint:** a 100 candidati risolti, report di P5.05 e decisioni preregistrate (sblocco di β, D-002 e D-003).
- **Accettazione:** `cycles` cresce senza buchi oltre quelli registrati; report a 100 candidati presentato com'è, anche se negativo.
- **Rischio:** medio: buchi nella serie (vedi rischi).
- **Dipendenze:** P5.01, P5.05.

### P5.11 — [CONFERMA ESPLICITA UTENTE] Esecuzione su conto demo
- **Obiettivo:** misurare il costo reale e lo scarto tra esito virtuale e fill.
- **Procedura:**
  1. Tu imposti nel tuo `.env` i due flag del doppio consenso. Claude non li tocca e le regole deny lo bloccano comunque.
  2. Dai la conferma nella conversazione.
  3. Si riconcilia con P3.34.
- **Accettazione:** report sullo scarto in R; se supera 0.1 R, nuova ADR secondo D-008.
- **Rischio:** alto: ordini reali su demo. Valgono il doppio consenso e la conferma umana.
- **Dipendenze:** P5.10, P3.16.

---

## Blocco 7 — Dashboard HTML statica (Fase 6)

### P6.01 — View-model dall'archivio
- **Obiettivo:** `report/viewmodel.py`, funzione pura archivio → dizionario con:
  - ultimi segnali, rischio ed esposizione;
  - curve netta e lorda;
  - calibrazione e confronto tra varianti;
  - copertura della serie.
- **Test prima:** `test_viewmodel_on_fake_archive_hand_computed` (ogni numero calcolato a mano) e `test_no_llm_confidence_in_viewmodel`.
- **File:** creati `report/__init__.py`, `report/viewmodel.py`, `tests/report/test_viewmodel.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/report -q`
- **Rischio:** basso.
- **Dipendenze:** P5.05.

### P6.02 — Rendering HTML con la skill frontend-design
- **Obiettivo:** `report/dashboard.py::render(vm) -> str` con `string.Template` e Plotly `to_html` con JS incorporato (funziona offline).
  - Layout a colonna singola per il telefono, `meta viewport`.
  - Stile curato con la skill `frontend-design`.
- **Test prima:**
  - `test_snapshot_matches` (`tests/report/snapshots/dashboard.html`, rigenerabile solo con un flag esplicito e revisione del diff);
  - `test_every_viewmodel_number_rendered`;
  - `test_no_external_urls`;
  - `test_viewport_meta_present`.
- **File:** creati `report/dashboard.py`, `report/template.html` e il test.
- **Accettazione:** `.venv\Scripts\python -m pytest tests/report -q`
- **Rischio:** basso. Snapshot fragili: per renderli stabili si fissano gli id dei div Plotly.
- **Dipendenze:** P6.01.

### P6.03 — [UTENTE] Generazione a fine ciclo e rimozione di Streamlit
- **Obiettivo:**
  - scrittura atomica di `data/dashboard.html` (file temporaneo + `os.replace`) a fine ciclo;
  - rimozione di `dashboard.py` e di streamlit da `requirements.txt` (**con la tua conferma**);
  - accesso dal telefono a cura tua (Tailscale o cartella sincronizzata), senza hosting pubblico.
- **Test prima:** `test_atomic_write_no_partial_file` e `test_cycle_triggers_dashboard_generation`.
- **File:** modificati `app/scheduler.py`, `requirements.txt`; rimosso `dashboard.py`.
- **Accettazione:** `.venv\Scripts\python -m pytest -q`
- **Rischio:** basso.
- **Dipendenze:** P6.02.

---

## Blocco 8 — Revisione e pubblicazione (Fase 7)

### P7.01 — Review del codice
- **Obiettivo:** eseguire `/code-review`, `/ecc:python-review` ed `ecc:verification-loop`; ogni correzione in un commit separato, con TDD.
- **Accettazione:**
  - review senza rilievi critici aperti;
  - `.venv\Scripts\python -m pytest -q` verde;
  - copertura del dominio ≥ 85%.
- **Rischio:** basso.
- **Dipendenze:** tutti i passi precedenti.

### P7.02 — [UTENTE] Security scan e T-001
- **Obiettivo:**
  - eseguire `/ecc:security-scan`;
  - verificare che nella storia non ci siano segreti (`git log --all -- .env`, ricerca di pattern di chiavi);
  - **su tua conferma:** `git rm --cached logs/signals_history.json logs/backtest_*.csv`. I file restano su disco.
- **Accettazione:** scan pulito; `git ls-files logs` senza JSON né CSV.
- **Rischio:** medio. Se si trova un segreto nella storia serve una tua decisione: rotazione della chiave e riscrittura della storia, mai force-push senza chiedere.
- **Dipendenze:** P7.01.

### P7.03 — [UTENTE] README onesto e chiusura
- **Obiettivo:**
  - README con architettura, come si esegue (solo DRY_RUN), risultati reali con intervalli (anche negativi o non concludenti) e limiti;
  - promemoria per l'email noreply di GitHub (T-003) e decisione su T-005;
  - aggiornamento di PROGRESS.md e DECISIONS.md;
  - push **solo su tua conferma**.
- **Accettazione:** il README non contiene numeri che non vengano dal report; T-001, T-003 e T-006 chiusi.
- **Rischio:** basso.
- **Dipendenze:** P7.02.

---

## Tabella riassuntiva

| ID | Titolo | Rischio | Dipendenze |
|---|---|---|---|
| P3.01 | Ambiente dev e guardie dei test | basso | — |
| P3.02 | Doppio consenso nell'executor (T-006) | medio | P3.01 |
| P3.03 | Direzione TP/SL (T-004) | medio | P3.01 |
| P3.04 | Diagnosi fuso MT5 (T-007) | basso | P3.01 |
| P3.05 | [UTENTE] Fuso reale sul terminale | basso | P3.04 |
| P3.06 | Tipi di dominio | basso | P3.03, P3.04 |
| P3.07 | Pip per coppia, conto EUR | medio | P3.06 |
| P3.08 | Costi, R ed esito | basso | P3.07 |
| P3.09 | Rischio (hypothesis) | medio | P3.07, P3.08 |
| P3.10 | Esposizione (hypothesis) | basso | P3.06 |
| P4.01 | p0, W, L, p\*, EV | basso | P3.08 |
| P4.02 | Beta κ, p5, EV_5 | basso | P4.01 |
| P4.03 | Kelly λ e gate | basso | P4.02 |
| P4.04 | Logistica con offset, walk-forward, copertura | medio | P4.01–P4.03 |
| P3.11 | Porte dati/notizie, anti-futuro | basso | P3.06 |
| P3.12 | Porta LLM validata | basso | P3.11 |
| P3.13 | Porta broker, sim, doppio consenso | medio | P3.11, P3.02 |
| P3.14 | Porta archivio e contratto | basso | P3.11 |
| P3.15 | Adattatore dati MT5 | medio | P3.11, P3.04, P3.05 |
| P3.16 | Adattatore broker MT5 | alto | P3.13, P3.15 |
| P3.17 | LLM OpenAI-compatibile | basso | P3.12 |
| P3.18 | [UTENTE] Finnhub (T-008) | medio | P3.11 |
| P3.19 | SQLite schema D7 | basso | P3.14 |
| P3.20 | WAL e sola aggiunta | basso | P3.19 |
| P3.21 | [UTENTE] Config pydantic-settings | medio | P3.02 |
| P3.22 | Generatore di candidati | basso | P3.06, P3.21 |
| P3.23 | Estrattori a schema chiuso | basso | P3.12 |
| P3.24 | Prompt separati | basso | P3.23 |
| P3.25 | run_once: flusso | medio | P3.11–P3.14, P3.22–P3.24 |
| P3.26 | run_once: varianti e decisione | medio | P3.25, P4.03, P4.04, P3.09, P3.10 |
| P3.27 | Risoluzione virtuale | medio | P3.08, P3.25 |
| P3.28 | Scheduler e composizione | medio | P3.21, P3.25–P3.27 |
| P3.29 | [UTENTE] Migrazione dei 30 test | medio | P3.15–P3.28 |
| P3.30 | Via confidence.py e pipeline dashboard | basso | P3.26 |
| P3.31 | [UTENTE] Via moduli legacy | medio | P3.29, P3.30 |
| P3.32 | Input completo e replay | basso | P3.31 |
| P3.33 | Completezza llm_calls/candidates | basso | P3.32 |
| P3.34 | Costi reali e riconciliazione | basso | P3.33, P3.16 |
| P5.01 | [UTENTE] Preregistrazione | basso | P3.34 |
| P5.02 | Metriche | basso | P5.01 |
| P5.03 | Bootstrap e gruppi | basso | P5.02 |
| P5.04 | Variante 6 e disponibilità 4/5 | medio | P3.26 |
| P5.05 | Report | basso | P5.03, P5.04 |
| P5.06 | Backtest senza LLM | basso | P5.02, P4.04 |
| P5.07 | Giudice alla cieca | basso | P3.17, P3.33 |
| P5.08 | [UTENTE] Giudice offline | basso | P5.07, P3.20 |
| P5.09 | Metriche giudice e promozione | basso | P5.03, P5.08 |
| P5.10 | [UTENTE] Test in avanti in DRY_RUN | medio | P5.01, P5.05 |
| P5.11 | [CONFERMA] Demo | alto | P5.10, P3.16 |
| P6.01 | View-model | basso | P5.05 |
| P6.02 | Rendering HTML (frontend-design) | basso | P6.01 |
| P6.03 | [UTENTE] Generazione e via Streamlit | basso | P6.02 |
| P7.01 | Review | basso | tutti |
| P7.02 | [UTENTE] Security scan e T-001 | medio | P7.01 |
| P7.03 | [UTENTE] README e chiusura | basso | P7.02 |

## I 5 rischi di esecuzione del piano

1. **Formule della Fase 4 diverse dalla tua specifica.** P4.01–P4.04 sono scritte su formule dedotte (assunzione 1). Se sono sbagliate, i test obbligatori passano su un modello sbagliato.
   - *Mitigazione:* confermi le formule all'approvazione del piano; vanno nel docstring di `domain/probability.py` e in PREREGISTRAZIONE.md.
2. **Regressioni di sicurezza durante la transizione.** Per circa 30 passi convivono il vecchio flusso (`main.py`) e quello nuovo.
   - *Mitigazione:* P3.02 e P3.03 vengono prima di tutto; il test a proprietà sul doppio consenso resta attivo fino a P3.31 e poi si sposta sulla porta (P3.13) e sul costruttore MT5 (P3.16); il default resta sempre il broker simulato.
3. **Le regole deny bloccano passi legittimi** (stringa del flag nei comandi, modifiche a `.env.example`).
   - *Mitigazione:* nomi in minuscolo nei test, impostazione via argomenti e non via env da shell. Se un passo viene bloccato ci si ferma e si chiede a te, senza aggirare la regola. Le modifiche al tuo `.env` le fai tu (P3.21, P5.11).
4. **Bias del simulatore e del fuso orario** (ingresso alla chiusura, SL prioritario, costo, offset con l'ora legale), che invaliderebbe gli esiti virtuali su cui poggia Q-004.
   - *Mitigazione:* misura reale del fuso (P3.05), ricalcolo dell'offset a ogni ciclo (P3.15), colonna `spread`, riconciliazione con i fill demo (P3.34, P5.11) con la soglia di 0.1 R di D-008.
5. **Porting dei test che perde garanzie o le "aggiusta".** Alcuni valori attesi cambiano per correggere bug e alcuni test si ritirano.
   - *Mitigazione:* tabella di corrispondenza riga per riga (P3.29), tue conferme esplicite su (a), (b) e (c), test vecchi cancellati solo dopo che la regressione nuova è verde (P3.31), commit che dichiarano ogni cambio di asserzione.

Rischio residuo da tenere presente: la potenza statistica. Con 100 candidati il risultato probabile è "non concludente", e va riportato così: è previsto in PREREGISTRAZIONE.md.

## Log
- 2026-11-22: applicata la patch di sicurezza (commit `ab9c0b0` su main), creato il branch `ristrutturazione`. Fase 0 completata: 30 test verdi. Aggiunte le regole `permissions.deny` (verificate: il comando di prova viene bloccato).
- 2026-11-22: Fase 1 scritta: `docs/ALTERNATIVE.md` (D1–D12, matrici pesate) e ADR D-001…D-012 in stato Proposta. Trovati 2 problemi di sicurezza nuovi (T-006, T-007) e una contraddizione nella specifica della Fase 4 (Q-004).
- 2026-11-22: Fase 1 approvata dall'utente: D-001…D-012 accettate; Q-004 chiusa (candidati risolti virtualmente); fornitore del giudice remoto rimandato (Q-001).
- 2026-11-22: Fase 2 scritta: 55 passi (P3.01–P7.03). Formule della Fase 4 riallineate alla specifica (Kelly su p, distanze da ask/bid, attivazione con BSS > 0, confidenza P(p > p*)).
- 2026-11-22: piano approvato (incluse le tre conferme: rischio con costo, 0.50→0.55 lotti, ritiro dei test del giudice decisore).
- 2026-11-22: P3.01 fatto (0ad3cdd RED, 1733027 GREEN: 34 passed). P3.02 fatto (fe2b65c RED, 7b415a2 GREEN: 40 passed) — T-006 chiuso.
- 2026-11-22: P3.03 fatto (51d1817 RED, 21f63eb GREEN: 46 passed) — T-004 chiuso; aperto T-009 (R:R 1.5 esatto scartato per virgola mobile). P3.04 fatto (4a3677a RED, GREEN: 54 passed); pytest in modalità importlib.
- 2026-11-22: P3.06–P3.10 fatti (tipi, pip in EUR, costi ed esito, rischio, esposizione): 103 passed. T-009 risolto nel dominio con distanze arrotondate a 0.1 pip.
- 2026-11-22: P4.01–P4.04 fatti (domain/probability.py, domain/logistic.py): 140 passed; copertura del dominio 98% con soglia 85% in .coveragerc. Due correzioni dichiarate: strategia di un test a proprietà (differenze subnormali) e f* ≈ 1e-17 a p = p* trattato come zero nel codice.
- 2026-11-22: P3.11–P3.17 e P3.19–P3.20 fatti: porte (dati, notizie, LLM, broker, archivio) con contratti condivisi tra fake e adattatori; adattatori dati e broker MT5 (solo FakeMt5, nessuna richiesta inviata), LLM OpenAI-compatibile, archivio SQLite a sola aggiunta con WAL. 235 passed. Termini Finnhub verificati (T-008): serve la decisione dell'utente per P3.18.
