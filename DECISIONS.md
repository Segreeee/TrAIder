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

### D-013 — Replay dal solo input_json: candele grezze, stime come input  ·  Stato: Accettata  ·  2026-11-23
- **Contesto:** P3.32 chiede che ogni ciclo archiviato si possa rieseguire con lo stesso risultato.
- **Alternative:** ultime 20 barre con indicatori (stato precedente, non basta a rigenerare il candidato) / **candele grezze M15 e H1 + stime p/p5 per variante come input** / ricalcolo delle stime dallo storico (impossibile: lo storico risolto cresce dopo il ciclo).
- **Decisione e motivo:** si salvano candele grezze, notizie, conto, cambio EUR, valore del pip, costo, stime per variante e configurazione senza segreti né credenziali MT5; gli indicatori si ricalcolano. `app/replay.py` rigenera candidato e decisioni.
- **Conseguenze:** circa 25 KB per ciclo; il replay verifica generatore e decisione, non lo stimatore.
- **Cosa farebbe cambiare idea:** archivio troppo grande (si comprime il JSON) o bisogno di rieseguire anche la stima (si salva l'istantanea dello storico usato).

### D-014 — Esiti del broker in una tabella separata, costi con i segni di MT5  ·  Stato: Accettata  ·  2026-11-23
- **Contesto:** P3.34 vuole l'esito del broker accanto a quello virtuale, ma `outcomes` ha `candidate_id` come chiave primaria.
- **Alternative:** migrare `outcomes` a chiave (candidate_id, resolved_by) / **tabella `broker_outcomes`** / colonne in più in `executions` (vietato: sola aggiunta).
- **Decisione e motivo:** tabella nuova, creata da `CREATE TABLE IF NOT EXISTS` anche sull'archivio esistente, senza migrazioni. Commissione e swap con il segno di MT5 (negativo = pagato), così si sommano al profitto come in `account()`. Lo swap si registra alla chiusura (in `broker_outcomes`), perché all'ingresso vale sempre 0. Il broker simulato registra all'ingresso metà della commissione configurata, come il deal di ingresso MT5.
- **Conseguenze:** `outcomes.resolved_by = 'broker'` resta ammesso dallo schema ma non usato. L'ora di chiusura è quella di rilevazione; il cambio EUR è quello della riconciliazione.
- **Cosa farebbe cambiare idea:** scarti sistematici vicini alla soglia di 0.1 R dovuti a questi due limiti → ora del deal convertita con l'offset del server e cambio salvato all'ingresso.

### D-015 — Notizie live da una cache del ciclo precedente  ·  Stato: Accettata  ·  2026-11-23
- **Contesto:** review di fine Fase 3: il ciclo scarica le notizie dopo la chiusura, quindi fetched_at > chiusura e il filtro anti-futuro le scarta tutte; il macro non è mai partito.
- **Alternative:** **cache: ogni ciclo salva ciò che scarica, il successivo usa solo notizie già in cache prima della chiusura** / tolleranza di pochi secondi su fetched_at.
- **Decisione e motivo:** cache (scelta dell'utente). La regola anti-futuro resta rigorosa; costo: le notizie arrivano con una candela (15 min) di ritardo.
- **Cosa farebbe cambiare idea:** il ritardo rende il macro inutile nei dati (varianti 4/5 senza segnale) → ADR sulla tolleranza.

### D-016 — Posizioni del broker simulato ricavate dall'archivio  ·  Stato: Accettata  ·  2026-11-23
- **Contesto:** le posizioni simulate non si chiudevano mai: dopo 3 trade ogni candidato andava in HOLD MAX_POSITIONS.
- **Alternative:** **dall'archivio: eseguiti e non ancora risolti** / chiusura in memoria quando arriva l'esito.
- **Decisione e motivo:** dall'archivio (scelta dell'utente): sopravvivono ai riavvii e si chiudono con l'esito virtuale.
- **Nota:** proposto e rifiutato dall'utente un controllo "solo conto demo" nel broker MT5: restano doppio consenso e conferma nella conversazione.

### D-017 — Variante 6 (decisore legacy in ombra) non realizzata  ·  Stato: Accettata  ·  2026-11-23
- **Contesto:** P5.04 prevedeva il vecchio prompt decisore in sola ombra, per confronto con il sistema legacy.
- **Alternative:** **non farla** / farla dietro un flag disattivato di default.
- **Decisione e motivo:** scelta dell'utente: non farla. Costa una terza chiamata LLM per candidato (ciclo da ~4 a ~6 minuti su 6 simboli) e misura un ruolo, l'LLM decisore, già escluso da D-002. Il confronto con il legacy resta descrittivo (storico della vecchia dashboard).
- **Conseguenze:** P5.04 si riduce alla disponibilità delle varianti 4/5 nel report; la preregistrazione la esclude.
- **Cosa farebbe cambiare idea:** serve un confronto quantitativo con il vecchio sistema per il portfolio → nuova serie dedicata, mai a metà della raccolta.

## Domande aperte
- Q-001 — Fornitore del giudice remoto (campione 20%, D-012): lo sceglie l'utente. Fino ad allora solo giudice locale. Non blocca la Fase 2: la porta LLM è indipendente dal fornitore.
- Q-005 — Soglia di attivazione del modello logistico (2026-11-22, P3.26). La regola della specifica "Brier skill score > 0 fuori campione" si attiva **per caso**: con caratteristiche senza informazione (600 esiti, split 70/30) il BSS esce positivo in 4 semi su 10 (0.0002, 0.0015, 0.0044, 0.0096). Il gate su EV_5 resta una seconda protezione (il p5 da bootstrap è prudente), ma la regola da sola non distingue segnale da rumore. Proposte: (a) estremo inferiore di un intervallo bootstrap al 90% del BSS > 0; (b) soglia fissa, es. BSS ≥ 0.01; (c) test di rapporto di verosimiglianza contro β = 0 con p < 0.05. Raccomandazione: (a), coerente con l'uso di p5 nel gate. Il test `test_uninformative_features_keep_beta` è segnato xfail strict finché non si decide. **Chiusa il 2026-11-22: l'utente sceglie (a).**

## Domande chiuse
- Q-003 — Calendario macro: per ora nessuno (D-005 accettata così). Si riapre se compare una fonte gratuita con termini verificati o se l'utente accetta un costo.
- Q-004 — Gate EV con β=0: i 100 trade che sbloccano β sono **candidati risolti virtualmente**, eseguiti o no. Il sistema raccoglie dati senza operare finché EV_5 > EV_MIN. Approvato il 2026-11-22.

## TODO
| ID | Voce | Responsabile | Collegato a | Stato |
|----|------|--------------|-------------|-------|
| T-001 | `git rm --cached` di `logs/signals_history.json` e `logs/backtest_*.csv` (restano su disco) | claude, su conferma | Fase 7 | da fare |
| T-002 | `YahooNewsFeed` non usata: rimuoverla o tenerla come adattatore di prova | utente | D-005 | da fare |
| T-003 | Ricordare all'utente di configurare l'email "noreply" di GitHub per i commit | claude | Fase 7 | da fare |
| T-004 | Controllo della direzione di TP/SL mancante (`abs()` nel calcolo di R:R) | claude | Fase 3, primi passi | fatto (21f63eb) |
| T-005 | `.claude/` è in `.gitignore`: le regole deny valgono solo su questa macchina | utente | Guardrail | da decidere |
| T-006 | `ALLOW_LIVE_TRADING` non esiste nel codice: un solo flag basta per ordini reali | claude | Fase 3, primo passo | fatto (7b415a2) |
| T-007 | Verificare il fuso orario delle barre MT5 contro UTC (può sfasare gli esiti, anche dei 21 trade) | claude → utente | Fase 3 | misurato il 2026-11-22 22:18 UTC: **scarto server − UTC = +2 ore** (barra M15 aperta alle 00:15 ora server). Conferma che MT5 restituisce l'ora del server, non UTC: il codice legacy trattava quei tempi come UTC, quindi i 21 trade storici hanno orari sfasati di 2 ore (3 in estate) e le loro risoluzioni vanno considerate non affidabili. Il nuovo adattatore converte in UTC ricalcolando lo scarto a ogni ciclo. **Chiuso il 2026-11-22 su decisione dell'utente:** il `.env` attuale è quello voluto e la misura vale per il server configurato |
| T-008 | Riconfermare sulle pagine ufficiali i termini e i limiti di Finnhub | claude → utente | D-005 | chiuso il 2026-11-22: l'utente sceglie **uso privato** (P3.18 si fa; i testi delle notizie restano in `data/`, in pubblico solo metriche aggregate) |
| T-009 | R:R esattamente 1.5 viene scartato per errore in virgola mobile (30/20 pip → 1.4999…): nel dominio usare distanze arrotondate al pip | claude | P3.08 / P4.01 | fatto nel dominio (9d4ffa0); il gate legacy resta finché non viene sostituito |
| T-010 | Spread contato due volte nei BUY. Le distanze partono dal prezzo di esecuzione (ask per i BUY), ma c = spread + commissione + slippage include di nuovo lo spread: per i BUY si paga due volte (≈ 0.1 R con stop di 8 pip). Per i SELL il simulatore controlla l'uscita sul bid invece che sull'ask, e lo spread in c compensa. Risultato: asimmetria BUY/SELL nel gate e negli esiti virtuali, prudente ma distorta. Proposta: c senza spread quando le distanze partono dal prezzo di esecuzione, e uscite dei SELL controllate su bid + spread. Tocca le formule approvate: decide l'utente | utente | P3.26 / P3.27 | deciso il 2026-11-22: **correggere** (c senza spread, uscite SELL su ask) |
| T-011 | Ora legale del server MT5: `closed_bars` applica l'offset di adesso a tutte le barre, anche a quelle precedenti al cambio (±1 ora). Un candidato in attesa a cavallo del cambio verrebbe risolto su barre spostate (rischio di guardare il futuro). Serve l'offset per barra o il rifiuto di risolvere a cavallo del cambio. Scadenza: prima del 2027-03-14 (cambio dei server che seguono l'ora legale USA), o prima di P5.10 se il test in avanti lo attraversa | claude | R5 / P3.15 | da fare |
