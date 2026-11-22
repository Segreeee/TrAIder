# DECISIONS
ADR brevi, uno per decisione. Le decisioni accettate non si modificano: si sostituiscono con una nuova voce.
Le analisi complete con le matrici stanno in `docs/ALTERNATIVE.md`.

## Decisioni

### D-001 — Architettura esagonale leggera  ·  Stato: Accettata  ·  2026-11-22
- **Contesto:** tre pipeline divergenti (main, dashboard, backtester); test che sostituiscono variabili di modulo.
- **Alternative:** moduli ripuliti (68.0) / **esagonale leggera (82.4)** / eventi (62.0) / LangGraph (61.4).
- **Decisione e motivo:** dominio puro + 5 porte `Protocol` (dati, notizie, LLM, broker, archivio) con adattatore reale e finto, una radice di composizione, `run_once` come Facade, varianti come Strategy. Massima testabilità; un solo punto per il doppio consenso sugli ordini.
- **Conseguenze:** più file; nessun framework di iniezione delle dipendenze.
- **Cosa farebbe cambiare idea:** cicli reali nel flusso → LangGraph; più processi → eventi.
- **Playbook:** patterns/adapter.md, patterns/facade.md, patterns/strategy.md, testing.md §4.

### D-002 — LLM come estrattori di caratteristiche  ·  Stato: Accettata  ·  2026-11-22
- **Contesto:** Brier della confidenza LLM 0.360 contro 0.250 della costante; l'LLM sceglie azione, livelli e lotto insieme.
- **Alternative:** decisori (54.6) / **estrattori (79.6)** / solo spiegazione (76.6).
- **Decisione e motivo:** schema chiuso `{direzione, forza, orizzonte, motivazioni}`; direzione e livelli dal generatore di candidati della baseline; caratteristica con segno nel modello. Ogni contributo LLM è misurabile con un'ablation.
- **Conseguenze:** l'LLM non decide più livelli né lotto; la confidenza dichiarata sparisce dallo schema.
- **Cosa farebbe cambiare idea:** β LLM con intervallo che include 0 e Brier skill score ≤ 0 dopo 100 candidati → solo spiegazione; output non validi > 5% → altro modello.

### D-003 — Combinazione: logistica calibrata, baseline tecnica in ombra  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** giudice LLM (51.2) / consenso (74.2) / **logistica + Beta (85.8)** / baseline pura (84.2).
- **Decisione e motivo:** modello di probabilità della Fase 4 (Beta con κ≈20 sotto i 100 candidati, poi L2 walk-forward); baseline sempre calcolata come riferimento. Con β=0 le due coincidono. `core/confidence.py` va eliminato.
- **Cosa farebbe cambiare idea:** Brier skill score contro baseline + p0 ≤ 0 fuori campione → in produzione resta la baseline.

### D-004 — Separazione degli analisti per dati, attivata per gradi  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** **dati diversi (80.0)** / modelli diversi (61.8) / uno solo (75.8) / entrambi (67.6).
- **Decisione e motivo:** il tecnico vede solo prezzi, indicatori e trend sul timeframe superiore; il macro solo notizie con `fetched_at` (niente prezzi). Si parte con il solo tecnico finché D-005 non è attivo. Due modelli 12B non stanno in 4 GB di VRAM.
- **Cosa farebbe cambiare idea:** kappa tecnico-macro > 0.8 → aggiungere un modello diverso (Qwen remoto).

### D-005 — Notizie: Finnhub dietro la porta, "nessuna" come default  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** nessuna (78.4) / **Finnhub (81.0)** / più fonti (72.2) / calendario (67.4).
- **Decisione e motivo:** a parità di punteggio decide la Fase 5 (serve la variante "solo macro"). Si registrano `published_at` e `fetched_at`; in un ciclo si usano solo notizie con `fetched_at ≤ chiusura della candela`. Licenza personale: il testo delle notizie non entra mai nella repo. Forex Factory è escluso per i termini d'uso.
- **Conseguenze:** chiave `FINNHUB_API_KEY` in env; `YahooNewsFeed` da rimuovere o declassare (T-002).
- **Cosa farebbe cambiare idea:** termini ufficiali incompatibili, o meno di 5 notizie forex al giorno → più fonti con GDELT; costo mensile accettato → calendario.

### D-006 — Broker: MT5 + broker simulato dietro la stessa porta  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** MT5 (77.8) / cTrader Open API (71.4) / TradingView (41.6) / simulato (80.6). Escluse le FIX API (volumi richiesti).
- **Decisione e motivo:** il simulato è il default (DRY_RUN e Fase 5); MT5 serve per il demo, per misurare il costo reale. La porta applica `DRY_RUN=false` + `ALLOW_LIVE_TRADING=true`, coperta da test. Il demo richiede la conferma dell'utente.
- **Cosa farebbe cambiare idea:** esecuzione su Linux/cloud o disconnessioni MT5 frequenti → cTrader.

### D-007 — Archivio in SQLite (WAL)  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** JSONL (65.0) / **SQLite (91.0)** / DuckDB (80.0) / PostgreSQL (72.4).
- **Decisione e motivo:** ACID, vincoli, idempotenza `UNIQUE(symbol, candle_close_utc)`, `:memory:` nei test, nessuna dipendenza nuova. Tabelle: `cycles`, `llm_calls`, `candidates`, `executions`, `outcomes`. Il file sta in `data/`, ignorato da git.
- **Cosa farebbe cambiare idea:** query > 10 s o più di 1 milione di righe → copia DuckDB/Parquet in lettura.

### D-008 — Valutazione ibrida: backtest solo senza LLM, in avanti per gli LLM  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** backtest proprio (70.2) / libreria (64.2) / solo in avanti (78.2) / **ibrido (89.4)**.
- **Decisione e motivo:** baseline, p0, Beta e β tecnici si backtestano; tutto ciò che usa LLM solo in avanti, dopo la data di addestramento, con `model_digest` registrato. Stesso simulatore di esito per tutti, varianti appaiate, metriche preregistrate.
- **Conseguenze:** circa 300 trade per distinguere un tasso di TP del 45% dal 38% (calcolo di potenza); 100 trade rilevano solo differenze di circa 12 punti.
- **Cosa farebbe cambiare idea:** scarto virtuale-fill demo > 0.1 R → fonte di verità diventa il demo eseguito.

### D-009 — Dashboard come HTML statico generato dall'archivio  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** Streamlit (73.2) / FastAPI+React (64.8) / **HTML statico (86.0)** / Grafana (67.2).
- **Decisione e motivo:** nessun server né input; si apre offline su telefono; funzione pura testabile con snapshot. Niente hosting pubblico (dati del conto).
- **Cosa farebbe cambiare idea:** azioni dal telefono → Streamlit con autenticazione.

### D-010 — Ciclo allineato alla candela, idempotente  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** while (57.4) / APScheduler (74.8) / Utilità di pianificazione (75.6) / **allineato stdlib (85.6)**.
- **Decisione e motivo:** `next_run` funzione pura; chiusura della candela letta dalla barra MT5; candele perse mai recuperate con l'LLM. L'Utilità di pianificazione fa da supervisore.
- **Cosa farebbe cambiare idea:** più di 2 calendari → APScheduler.

### D-011 — Configurazione con pydantic-settings  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** dataclass (58.6) / **pydantic-settings (91.0)** / dataclass validata (81.6) / TOML + env (75.6).
- **Decisione e motivo:** validazione all'avvio, `SecretStr`, validatore incrociato sul doppio consenso, `config_hash` senza segreti in archivio. Un'istanza passata come argomento.
- **Cosa farebbe cambiare idea:** divieto di nuove dipendenze → dataclass validata.

### D-012 — LLM-as-a-judge: revisore offline con veto ombra  ·  Stato: Accettata  ·  2026-11-22
- **Alternative:** decisore (51.2) / veto in linea (75.6) / **offline, veto ombra (87.0)** / caratteristica (78.6). Modello: gemma3 (68.8) / Qwen remoto (72.0) / **locale di altra famiglia, in lotti (79.0)**.
- **Decisione e motivo:** il revisore non decide: produce `{veto, checks}` alla cieca, offline, su tutti i candidati; i controlli deterministici sono codice. Si registrano veto ombra ed esito virtuale, così l'ablation non costa nulla. Un giudice remoto su un campione del 20% per l'accordo tra giudici: **fornitore da scegliere dall'utente** (porta LLM indipendente dal fornitore, client OpenAI-compatibile).
- **Conseguenze:** metriche preregistrate (precisione dei veti, ablation, stabilità, bias di posizione e di etichetta, kappa, AUC delle motivazioni).
- **Cosa farebbe cambiare idea:** promozione a veto in linea con ≥30 vetati / ≥100 candidati, lift con intervallo che esclude 1, ΔEV con intervallo che esclude 0, stabilità ≥ 95%, bias di posizione < 5%. Kappa < 0.4 → linea giudice archiviata.

## Domande aperte
- Q-001 — Fornitore del giudice remoto (campione 20%, D-012): lo sceglie l'utente. Fino ad allora solo giudice locale. Non blocca la Fase 2: la porta LLM è indipendente dal fornitore.

## Domande chiuse
- Q-003 — Calendario macro: per ora nessuno (D-005 accettata così). Si riapre se compare una fonte gratuita con termini verificati o se l'utente accetta un costo.
- Q-004 — Gate EV con β=0: i 100 trade che sbloccano β sono **candidati risolti virtualmente**, eseguiti o no. Il sistema raccoglie dati senza operare finché EV_5 > EV_MIN. Approvato il 2026-11-22.

## TODO
| ID | Voce | Responsabile | Collegato a | Stato |
|----|------|--------------|-------------|-------|
| T-001 | `git rm --cached` di `logs/signals_history.json` e `logs/backtest_*.csv` (restano su disco) | claude, su conferma | Fase 7 | da fare |
| T-002 | `YahooNewsFeed` non usata: rimuoverla o tenerla come adattatore di prova | utente | D-005 | da fare |
| T-003 | Ricordare all'utente di configurare l'email "noreply" di GitHub per i commit | claude | Fase 7 | da fare |
| T-004 | Controllo della direzione di TP/SL mancante (`abs()` nel calcolo di R:R) | claude | Fase 3, primi passi | da fare |
| T-005 | `.claude/` è in `.gitignore`: le regole deny valgono solo su questa macchina | utente | Guardrail | da decidere |
| T-006 | `ALLOW_LIVE_TRADING` non esiste nel codice: un solo flag basta per ordini reali | claude | Fase 3, primo passo | fatto (7b415a2) |
| T-007 | Verificare il fuso orario delle barre MT5 contro UTC (può sfasare gli esiti, anche dei 21 trade) | claude | Fase 3 | da fare |
| T-008 | Riconfermare sulle pagine ufficiali i termini e i limiti di Finnhub | claude | D-005 | da fare |
