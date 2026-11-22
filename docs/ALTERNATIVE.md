# TrAIder — Analisi delle alternative (Fase 1)

Data: 2026-11-22 · Branch `ristrutturazione` · Nessun codice modificato in questa fase.
Analisi di D1–D4 e D7–D12: agente `ecc:architect` su lettura completa del repo e del playbook
(`~/.claude/playbooks/ingegneria-informatica/`). D5 e D6: ricerche web, con fonti in fondo.
Gli ADR corrispondenti sono in `DECISIONS.md`, con stato **Proposta** fino all'approvazione.

## Metodo

Punteggio da 1 a 5 per criterio, dove 5 è il migliore. Per complessità, tempo di sviluppo, costo per segnale e latenza, 5 significa più basso o più conveniente.

**Totale pesato** = Σ(punteggio × peso) / 5, su 100.

| Criterio | Peso | Perché questo peso |
|---|---|---|
| Correttezza | 20 | Un segnale sbagliato o calcolato su dati futuri invalida tutto il resto |
| Misurabilità | 15 | Lo scopo è sapere se c'è vantaggio dopo i costi |
| Sicurezza operativa | 15 | Ordini reali e denaro |
| Testabilità | 12 | Vincolo TDD e test senza rete/MT5/LLM |
| Valore portfolio | 12 | Obiettivo dichiarato del progetto |
| Complessità | 10 | Un solo sviluppatore, una sola macchina |
| Tempo di sviluppo | 8 | |
| Costo per segnale | 5 | LLM locali: il costo è soprattutto tempo macchina |
| Latenza | 3 | Timeframe M15: conta solo se supera la finestra |

I punteggi sono giudizi motivati, non misure. Differenze sotto i 3-4 punti sono dentro l'incertezza, e in quei casi decide il criterio indicato nella raccomandazione. Nessun numero sperimentale è nuovo: le stime sono marcate come tali.

---

## 0. Problemi trovati nel codice che condizionano le decisioni

Questi problemi non erano nell'elenco iniziale. Quelli marcati ✔ sono stati verificati a mano.

1. ✔ **`ALLOW_LIVE_TRADING` non esiste nel codice.** In [core/executor.py:44](../core/executor.py#L44) bastano `dry_run=False` e MT5 importabile per inviare ordini reali. Il doppio consenso è solo scritto in CLAUDE.md. **Va chiuso per primo in Fase 3.**
2. ✔ **R:R senza controllo della direzione:** `abs()` in [core/risk_manager.py](../core/risk_manager.py) (T-004). Il valore è usato anche in `confidence.py` e `executor.py`.
3. **Pip fisso a 10 USD** su un conto in EUR ([core/risk_manager.py](../core/risk_manager.py)).
4. **Lo storico JSON perde dati:** conserva solo gli ultimi 200 segnali; un file corrotto viene letto come `[]` e poi sovrascritto; la scrittura non è atomica ([dashboard.py](../dashboard.py)).
5. **La confidenza dichiarata dall'LLM entra nelle decisioni:** ordina i candidati nella dashboard e il giudice la vede nel prompt.
6. **Il giudice rifà l'analisi da capo:** riceve tutto il prompt di mercato, con etichette non anonime e regole di arbitraggio scritte in prosa.
7. **Analisti non separati:** stesso `base_prompt`. Con `NEWS_PROVIDER=none` la pipeline reale è **1 analista tecnico + giudice**.
8. **Temperatura 0.2/0.3, non 0;** versione di modello e prompt non registrate.
9. **Tre pipeline divergenti:** `main.py` (un simbolo), `dashboard.py` (flusso proprio, senza capitale reale, esposizione né limite giornaliero), `core/backtester.py` (solo giudice).
10. **Il ciclo deriva:** `sleep(900)` parte dopo un ciclo che dura minuti. Non è allineato alla candela e non è idempotente.
11. **Configurazione:**
    - letta all'import;
    - nessuna validazione;
    - la `repr` del dataclass espone `qwen_api_key` e `mt5_password`.
12. ✔ **Orari:**
    - `_normalize_rates` produce orari naive nell'ora del server MT5 e li confronta con UTC: da verificare, perché può sfasare la risoluzione degli esiti, compresi i 21 trade;
    - scarta la colonna `spread` di MT5, utile per costi realistici ([core/data_feed.py:144-157](../core/data_feed.py#L144-L157)).
13. **Ambiente:** mancano pytest, hypothesis, coverage, scikit-learn e pydantic-settings, e manca `requirements-dev.txt`. pydantic 2.x è già presente (dipendenza di openai).

---

## D1 — Architettura

Alternative:
- **A. Moduli ripuliti:** dominio estratto e dipendenze passate come argomento.
- **B. Esagonale leggera:** 5 porte come `typing.Protocol` (dati, notizie, LLM, broker, archivio), una radice di composizione, nessun framework di iniezione delle dipendenze.
- **C. Pipeline a eventi.**
- **D. Grafo di stati (LangGraph).**

| Criterio | Peso | A Ripuliti | B Esagonale | C Eventi | D LangGraph |
|---|---|---|---|---|---|
| Correttezza | 20 | 3 | 4 | 3 | 3 |
| Misurabilità | 15 | 3 | 4 | 4 | 3 |
| Sicurezza operativa | 15 | 3 | 4 | 3 | 3 |
| Testabilità | 12 | 3 | 5 | 3 | 3 |
| Valore portfolio | 12 | 2 | 4 | 3 | 4 |
| Complessità | 10 | 5 | 4 | 2 | 2 |
| Tempo di sviluppo | 8 | 5 | 3 | 2 | 2 |
| Costo per segnale | 5 | 5 | 5 | 5 | 5 |
| Latenza | 3 | 5 | 5 | 4 | 4 |
| **Totale** | | **68.0** | **82.4** | **62.0** | **61.4** |

- **A, testabilità 3:** senza porte i test devono sostituire variabili di modulo (`ex.mt5 = FakeMt5()`), una tecnica fragile.
- **B, sicurezza 4:** con una sola porta broker c'è un solo punto in cui applicare il doppio consenso.
- **B, testabilità 5:** Adapter a oggetti con stub e driver (`patterns/adapter.md`, `testing.md` §4).
- **C, correttezza 3:** su un flusso lineare di 6 passi, ordinamento e idempotenza diventano un problema senza dare benefici.
- **D, portfolio 4:** riconoscibile, ma senza cicli né strumenti sarebbe una catena lineare scritta con un framework (Golden Hammer).

**Raccomandazione: B leggera.**
- `domain/` puro: tipi, pip, costi, probabilità, rischio, esposizione.
- 5 porte, ciascuna con un adattatore reale e uno finto.
- `run_once(candle)` come Facade.
- Le varianti di combinazione come Strategy.
- Input validati all'ingresso con schemi pydantic (`contracts.md`).

**Cosa farebbe cambiare idea:**
- cicli reali nel flusso, con più di 2 rami condizionali o uso di strumenti da parte dell'agente → D;
- più processi o macchine → C;
- una porta resta senza un secondo adattatore e senza test → torna ad A per quella porta.

---

## D2 — Ruolo degli LLM

Alternative:
- **A. Decisori**, come oggi.
- **B. Estrattori di caratteristiche:** schema chiuso `{direzione ∈ {-1,0,+1}, forza ∈ {0..3}, orizzonte, motivazioni}`. Livelli, lotto e decisione li calcola il codice.
- **C. Solo spiegazione.**

| Criterio | Peso | A Decisori | B Estrattori | C Spiegazione |
|---|---|---|---|---|
| Correttezza | 20 | 2 | 4 | 4 |
| Misurabilità | 15 | 2 | 5 | 2 |
| Sicurezza operativa | 15 | 2 | 4 | 5 |
| Testabilità | 12 | 3 | 4 | 5 |
| Valore portfolio | 12 | 3 | 5 | 2 |
| Complessità | 10 | 4 | 3 | 5 |
| Tempo di sviluppo | 8 | 5 | 3 | 4 |
| Costo per segnale | 5 | 3 | 3 | 4 |
| Latenza | 3 | 2 | 2 | 4 |
| **Totale** | | **54.6** | **79.6** | **76.6** |

- **A, correttezza 2:** sui 21 trade, Brier 0.360 contro 0.250 della costante 0.5. In più l'LLM sceglie TP e SL, e il gate R:R non controlla la direzione.
- **A, misurabilità 2:** azione, livelli e lotto escono insieme, quindi non si può attribuire l'esito a una componente.
- **B, misurabilità 5:** ogni caratteristica ha un β e si può fare un'ablation sugli stessi momenti.
- **C, misurabilità 2:** non risponde alla domanda centrale, cioè se l'LLM aggiunge informazione.

**Raccomandazione: B.**
- Con β=0, B si comporta come C più p0, ma intanto registra le caratteristiche LLM.
- Direzione e livelli (SL e TP come multipli di ATR) vengono dal generatore di candidati della baseline (D3-D).
- L'LLM entra come caratteristica con segno, per esempio `x = dir_llm · dir_candidato · forza`.
- Così ogni variante si valuta sugli stessi candidati (confronto appaiato).

**Cosa farebbe cambiare idea:**
- dopo almeno 100 candidati risolti in avanti, l'intervallo di confidenza 95% del β LLM include 0 e il Brier skill score contro p0 è ≤ 0 → C;
- output non validi > 5% anche con schema e temperatura 0 → valutare Qwen per l'estrazione.

---

## D3 — Combinazione dei segnali

Alternative:
- **A. LLM giudice.**
- **B. Regola di consenso.**
- **C. Logistica calibrata**, con la variante Beta a pochi dati della Fase 4.
- **D. Nessun LLM:** baseline tecnica pura, obbligatoria come riferimento.

| Criterio | Peso | A Giudice | B Consenso | C Logistica + Beta | D Baseline |
|---|---|---|---|---|---|
| Correttezza | 20 | 2 | 3 | 5 | 4 |
| Misurabilità | 15 | 2 | 3 | 5 | 4 |
| Sicurezza operativa | 15 | 2 | 4 | 4 | 5 |
| Testabilità | 12 | 2 | 5 | 4 | 5 |
| Valore portfolio | 12 | 3 | 2 | 5 | 2 |
| Complessità | 10 | 4 | 5 | 3 | 5 |
| Tempo di sviluppo | 8 | 5 | 5 | 3 | 4 |
| Costo per segnale | 5 | 2 | 4 | 4 | 5 |
| Latenza | 3 | 2 | 4 | 4 | 5 |
| **Totale** | | **51.2** | **74.2** | **85.8** | **84.2** |

- **A, testabilità 2:** l'arbitraggio è prosa nel system prompt e nessun test può verificarlo.
- **B, correttezza 3:** con il macro escluso, il "consenso" di un solo analista non dice nulla. È più utile come caratteristica (accordo sì/no).
- **C, correttezza 5:** è un modello di probabilità valutato con una regola di punteggio propria, e si testa come funzione pura. Proprietà hypothesis:
  - con β=0 vale p=p0;
  - p è monotòna in ogni x con β>0;
  - p ∈ (0,1).
- **D, misurabilità 4:** è l'unica parte che si può backtestare senza contaminazione (D8).
- `core/confidence.py` va **rimosso**, non ritoccato: indicatori correlati, pesi a mano, premio a un R:R alto che invece abbassa p0.

**Raccomandazione: C, con D sempre in parallelo in modalità ombra.** Lo scarto di 1.6 punti è dentro l'incertezza: decideranno i dati. C con β=0 coincide con D più p0. Si parte con la Beta (κ≈20) e si passa alla logistica L2 walk-forward oltre 100 candidati risolti.

**Cosa farebbe cambiare idea:**
- Brier skill score di C contro D più p0 ≤ 0 fuori campione su almeno 100 candidati → in produzione resta D;
- β che cambiano segno tra finestre consecutive in più del 30% delle caratteristiche → resta la Beta.

---

## D4 — Separazione reale degli analisti

Alternative:
- **A. Dati diversi:** il tecnico vede prezzi, indicatori e trend sul timeframe superiore; il macro solo notizie con timestamp e calendario, senza prezzi.
- **B. Modelli diversi.**
- **C. Un solo analista**, che è lo stato di fatto.
- **D. A + B.**

| Criterio | Peso | A Dati diversi | B Modelli diversi | C Uno solo | D A+B |
|---|---|---|---|---|---|
| Correttezza | 20 | 4 | 3 | 3 | 4 |
| Misurabilità | 15 | 4 | 3 | 3 | 3 |
| Sicurezza operativa | 15 | 4 | 3 | 4 | 4 |
| Testabilità | 12 | 4 | 4 | 5 | 4 |
| Valore portfolio | 12 | 4 | 3 | 2 | 4 |
| Complessità | 10 | 4 | 3 | 5 | 2 |
| Tempo di sviluppo | 8 | 4 | 4 | 5 | 3 |
| Costo per segnale | 5 | 4 | 2 | 5 | 2 |
| Latenza | 3 | 4 | 1 | 5 | 1 |
| **Totale** | | **80.0** | **61.8** | **75.8** | **67.6** |

- **A, correttezza 4:** separare le informazioni rende gli errori meno correlati. Un test sul costruttore di prompt verifica che il prompt macro non contenga numeri OHLC.
- **B, latenza 1:** due modelli 12B non stanno insieme in 4 GB di VRAM (stima: circa 7-8 GB ciascuno). Ogni ciclo pagherebbe un cambio di modello, che costa minuti.
- **B, correttezza 3:** modelli diversi che leggono gli stessi numeri restano correlati.

**Raccomandazione: A, introdotta per gradi.** Si parte da C e si attiva il macro solo con un adattatore notizie che registra `published_at` e `fetched_at` (D5). La diversità di modello resta un braccio sperimentale opzionale (Qwen remoto).

**Cosa farebbe cambiare idea:**
- kappa di Cohen tecnico-macro > 0.8 su almeno 100 candidati → la separazione non produce indipendenza, provare B;
- costo di Qwen per candidato sotto la soglia che fissa l'utente, con latenza p95 < 60 s → B remoto.

---

## D5 — Fonte delle notizie

Alternative:
- **A. Nessuna:** default attuale, macro escluso.
- **B. Finnhub** `/news?category=forex`.
- **C. Più fonti:** Finnhub + GDELT DOC 2.0 + Marketaux.
- **D. Calendario macroeconomico.**

Condizioni d'uso e limiti, verificati su fonti per lo più secondarie: **da riconfermare sulle pagine ufficiali prima di scrivere l'adattatore**.

| Fonte | Gratis | Limiti | Timestamp | Note |
|---|---|---|---|---|
| Finnhub | Sì, **uso personale non commerciale** | ~60 chiamate/min, tetto globale 30/s | `datetime` UNIX (docs ufficiali) | Categoria `forex`; storico notizie ~1 anno. Calendario economico probabilmente a pagamento (modulo ~50 $/mese, non verificato) |
| GDELT DOC 2.0 | Sì, senza chiave | ~1 richiesta ogni 5 s (fonte terza) | `seendate` UTC | Notizie generiche, molto rumorose; termini di licenza non verificati |
| Marketaux | Sì | ~100 richieste/giorno, 3 articoli/richiesta | da verificare | Etichette di entità forex e sentiment |
| Alpha Vantage | Sì | 25 richieste/giorno | — | `NEWS_SENTIMENT` forse premium |
| FMP | Calendario **non** nel piano gratuito | — | — | Dal piano Starter |
| Trading Economics | No (calendario a pagamento) | — | Sì | Campi completi (actual/forecast/previous) |
| Forex Factory | Nessuna API ufficiale | — | — | **Le avvertenze del sito vietano di copiare il calendario**: escluso |

| Criterio | Peso | A Nessuna | B Finnhub | C Più fonti | D Calendario |
|---|---|---|---|---|---|
| Correttezza | 20 | 5 | 4 | 4 | 3 |
| Misurabilità | 15 | 1 | 4 | 5 | 4 |
| Sicurezza operativa | 15 | 5 | 4 | 3 | 3 |
| Testabilità | 12 | 5 | 4 | 3 | 4 |
| Valore portfolio | 12 | 1 | 4 | 5 | 4 |
| Complessità | 10 | 5 | 4 | 2 | 3 |
| Tempo di sviluppo | 8 | 5 | 4 | 2 | 3 |
| Costo per segnale | 5 | 5 | 5 | 4 | 2 |
| Latenza | 3 | 5 | 4 | 3 | 4 |
| **Totale** | | **78.4** | **81.0** | **72.2** | **67.4** |

- **A, correttezza 5:** niente dati falsi e nessun rischio di vedere il futuro. Ma misurabilità 1: la variante "solo macro" della Fase 5 non si può fare.
- **B, correttezza 4 e non 5:** il `datetime` è la pubblicazione dichiarata dalla fonte, e una notizia può essere indicizzata in ritardo. **Regola anti-futuro:** registrare sia `published_at` sia `fetched_at`, e usare in un ciclo solo le notizie con `fetched_at ≤ chiusura della candela`. Nel test in avanti `fetched_at` è la verità.
- **B, sicurezza 4:** chiave API in env, dipendenza esterna, licenza personale. Il testo delle notizie resta nell'archivio locale e **non va mai nella repo**: si evita di ridistribuire i dati.
- **C, misurabilità 5:** permette l'ablation per fonte, ma triplica adattatori, deduplicazione e limiti da gestire.
- **D, correttezza 3:** le fonti gratuite hanno termini poco chiari, quelle affidabili sono a pagamento.

**Raccomandazione: B dietro la porta `NewsFeed`, con A come default di configurazione.** A e B sono a pari merito, e decide il requisito della Fase 5: senza B la variante "solo macro" non esiste. Il macro si accende solo con `NEWS_PROVIDER=finnhub`. Il calendario resta fuori finché non c'è una fonte gratuita con termini verificati (Q-003). `YahooNewsFeed` va rimossa, oppure tenuta solo come adattatore di prova: il suo `pubDate` non ha garanzie (T-002).

**Cosa farebbe cambiare idea:**
- i termini ufficiali di Finnhub escludono anche un uso personale pubblicato su GitHub, o la categoria `forex` restituisce meno di 5 notizie al giorno sulle coppie seguite → C con GDELT;
- l'utente accetta un costo mensile → D (Finnhub Economic o Trading Economics) per una finestra di esclusione attorno agli eventi ad alto impatto.

---

## D6 — Broker

Alternative:
- **A. MetaTrader5 Python:** solo Windows, già funzionante, demo Pepperstone in EUR.
- **B. cTrader Open API:** multipiattaforma, protobuf su TCP, registrazione di un'app OAuth, server demo separato.
- **C. TradingView + webhook:** gli avvisi pilotano un bridge.
- **D. Broker simulato (paper):** fill simulati su tick MT5 reali, nessun ordine.

Escluse: le FIX API Pepperstone, che richiedono volumi mensili enormi.

| Criterio | Peso | A MT5 | B cTrader | C TradingView | D Paper |
|---|---|---|---|---|---|
| Correttezza | 20 | 4 | 4 | 2 | 3 |
| Misurabilità | 15 | 4 | 4 | 2 | 4 |
| Sicurezza operativa | 15 | 4 | 4 | 2 | 5 |
| Testabilità | 12 | 3 | 3 | 2 | 5 |
| Valore portfolio | 12 | 3 | 4 | 2 | 3 |
| Complessità | 10 | 4 | 2 | 2 | 4 |
| Tempo di sviluppo | 8 | 5 | 2 | 2 | 4 |
| Costo per segnale | 5 | 5 | 5 | 3 | 5 |
| Latenza | 3 | 4 | 4 | 3 | 5 |
| **Totale** | | **77.8** | **71.4** | **41.6** | **80.6** |

- **A, testabilità 3:** il modulo `mt5` è globale; con la porta il problema si risolve.
- **A, portfolio 3:** legato a Windows.
- **B, complessità 2:** client protobuf/Twisted e token OAuth da gestire (segreti in più).
- **C:** i dati arrivano da TradingView e non dal broker, i webhook richiedono un endpoint pubblico, e probabilmente un piano TradingView a pagamento.
- **D, correttezza 3:** fill idealizzati. Lo spread si prende dal tick reale, ma non c'è slippage.

**Raccomandazione: A + D dietro la stessa porta `Broker`.** Non sono alternative ma due adattatori:
- **D** è il default per DRY_RUN e per tutta la Fase 5 finché l'utente non conferma il demo;
- **A** serve per il demo, per misurare il costo reale c dai fill;
- la porta applica il doppio consenso `DRY_RUN=false` + `ALLOW_LIVE_TRADING=true`, coperto da test;
- l'invio su demo richiede comunque la conferma dell'utente.

**Cosa farebbe cambiare idea:**
- serve far girare il sistema su Linux o in cloud → B;
- il terminale MT5 si disconnette più di una volta al giorno → B.

---

## D7 — Archivio dei segnali

Alternative:
- **A. JSONL** a sola aggiunta: lo stato attuale meriterebbe 1.
- **B. SQLite in WAL** (stdlib).
- **C. DuckDB.**
- **D. PostgreSQL.**

| Criterio | Peso | A JSONL | B SQLite | C DuckDB | D PostgreSQL |
|---|---|---|---|---|---|
| Correttezza | 20 | 3 | 5 | 3 | 5 |
| Misurabilità | 15 | 2 | 4 | 5 | 4 |
| Sicurezza operativa | 15 | 3 | 5 | 3 | 3 |
| Testabilità | 12 | 4 | 5 | 5 | 3 |
| Valore portfolio | 12 | 1 | 4 | 4 | 4 |
| Complessità | 10 | 5 | 4 | 4 | 2 |
| Tempo di sviluppo | 8 | 5 | 4 | 4 | 2 |
| Costo per segnale | 5 | 5 | 5 | 5 | 5 |
| Latenza | 3 | 5 | 5 | 5 | 4 |
| **Totale** | | **65.0** | **91.0** | **80.0** | **72.4** |

- **B, correttezza 5:** transazioni ACID; vincoli `CHECK`, `UNIQUE` e FK; chiave di idempotenza.
- **B, testabilità 5:** `:memory:` nei test.
- **C, correttezza e sicurezza 3:** un solo processo può scrivere, e demone e dashboard insieme entrano in conflitto.
- **D, sicurezza 3:** un servizio in più su Windows, con credenziali e backup.
- **Volume (stima):** circa 600 righe al giorno.

**Raccomandazione: B.** Schema minimo, a sola aggiunta salvo gli esiti:

1. **`cycles`**
   - Colonne: `cycle_id`, `symbol`, `candle_close_utc`, `candle_close_server`, `code_version` (git sha), `config_hash`, `input_json` (candele, indicatori, trend sul timeframe superiore, notizie con `published_at`/`fetched_at`, spread), `input_hash`, `started_at`, `finished_at`, `status`, `error`.
   - Vincolo: `UNIQUE(symbol, candle_close_utc)`.
2. **`llm_calls`**
   - Colonne: `call_id`, `cycle_id`, `role`, `provider`, `model`, `model_digest`, `prompt_version`, `prompt_text`, `temperature`, `seed`, `response_raw`, `parsed_json`, `schema_valid`, `latency_ms`, `tokens_in`, `tokens_out`, `cost_eur`, `error`.
3. **`candidates`**
   - Colonne: `candidate_id`, `cycle_id`, `variant`, `direction`, `entry_ref`, `sl`, `tp`, `d_sl`, `d_tp`, `p0`, `p`, `p5`, `ev`, `ev5`, `gate_passed`, `veto_shadow`, `final_action`, `lot`, `hold_reason`, `features_json`.
   - Vincolo: `UNIQUE(cycle_id, variant)`.
4. **`executions`**
   - Colonne: `candidate_id`, `mode` (paper/demo/live), `ticket`, `fill_price`, `spread`, `slippage`, `commission`, `swap`.
5. **`outcomes`**
   - Colonne: `candidate_id`, `resolution` (TP/SL/TIMEOUT), `exit_utc`, `exit_price`, `r_gross`, `r_net`, `cost_pips`, `resolved_by` (virtuale/broker).

Il file del database sta in `data/` ed è ignorato da git.

**Cosa farebbe cambiare idea:**
- query di analisi oltre 10 s, o più di 1 milione di righe → DuckDB in sola lettura su una copia, o export Parquet;
- più macchine che scrivono → PostgreSQL.

---

## D8 — Valutazione

Alternative:
- **A. Backtest proprio a eventi per tutto**, LLM compreso.
- **B. Libreria** (vectorbt, backtrader, backtesting.py).
- **C. Solo test in avanti su demo.**
- **D. Ibrido:** backtest solo per ciò che non usa LLM, test in avanti per il resto, stesso simulatore di esito.

| Criterio | Peso | A Backtest proprio | B Libreria | C Solo in avanti | D Ibrido |
|---|---|---|---|---|---|
| Correttezza | 20 | 2 | 2 | 5 | 5 |
| Misurabilità | 15 | 3 | 3 | 3 | 5 |
| Sicurezza operativa | 15 | 5 | 5 | 4 | 5 |
| Testabilità | 12 | 4 | 3 | 3 | 4 |
| Valore portfolio | 12 | 3 | 3 | 4 | 5 |
| Complessità | 10 | 4 | 3 | 4 | 3 |
| Tempo di sviluppo | 8 | 4 | 3 | 4 | 3 |
| Costo per segnale | 5 | 4 | 4 | 3 | 4 |
| Latenza | 3 | 5 | 5 | 5 | 5 |
| **Totale** | | **70.2** | **64.2** | **78.2** | **89.4** |

- **A e B, correttezza 2:** qualunque backtest LLM su dati precedenti alla data di addestramento è contaminato, qualunque sia il motore.
- **B, testabilità 3:** dipendenza pesante. Il loro stato di manutenzione è da verificare. Chiamare un LLM barra per barra non si adatta ai motori vettoriali.
- **C, misurabilità 3:** è lento. Calcolo di potenza (non un dato): per distinguere un tasso di TP del 45% dal 38% servono **circa 300 trade** (α=0.05 a una coda, potenza 0.8). Con 100 trade si rilevano solo differenze di circa 12 punti.
- **D, misurabilità 5:** tutte le varianti girano sugli stessi momenti, con esiti virtuali anche per i candidati non eseguiti. Il confronto è appaiato e la varianza più bassa.

**Raccomandazione: D.**
- **Si può backtestare:** generatore di candidati della baseline, p0, Beta, β delle caratteristiche tecniche (walk-forward), sensibilità ai costi con lo `spread` di MT5. Si riusa `simulate_outcome`, che in caso di ambiguità dà priorità allo SL, scelta prudente.
- **Solo in avanti:**
  - tutto ciò che contiene output LLM;
  - solo dopo la data di addestramento e di rilascio del modello, con `model_digest` registrato (un `ollama pull` può cambiare i pesi);
  - per Qwen remoto, una versione esplicita, non un alias.
- **Fonte di verità:** gli esiti virtuali nell'archivio. Sul demo, la riconciliazione con i fill misura lo scarto del simulatore.
- **Preregistrazione** prima di guardare i dati: metriche, soglia di 100 candidati, nessuna modifica di soglie in corsa.

**Cosa farebbe cambiare idea:**
- scarto medio tra esito virtuale e fill demo > 0.1 R per trade → la verità diventa il demo eseguito;
- un modello locale con data di addestramento documentata e successiva a uno storico abbastanza lungo → backtest LLM limitato a quella finestra.

---

## D9 — Dashboard (anche da telefono)

Alternative:
- **A. Streamlit**, in sola lettura dall'archivio.
- **B. FastAPI + React.**
- **C. HTML statico** generato dall'archivio a fine ciclo (Plotly + jinja2, già installati).
- **D. Grafana su SQLite.**

NiceGUI e Panel hanno lo stesso profilo di A.

| Criterio | Peso | A Streamlit | B FastAPI+React | C HTML statico | D Grafana |
|---|---|---|---|---|---|
| Correttezza | 20 | 4 | 4 | 4 | 4 |
| Misurabilità | 15 | 4 | 4 | 4 | 4 |
| Sicurezza operativa | 15 | 3 | 2 | 5 | 3 |
| Testabilità | 12 | 3 | 4 | 5 | 2 |
| Valore portfolio | 12 | 3 | 4 | 3 | 3 |
| Complessità | 10 | 4 | 1 | 5 | 3 |
| Tempo di sviluppo | 8 | 4 | 1 | 4 | 3 |
| Costo per segnale | 5 | 5 | 5 | 5 | 5 |
| Latenza | 3 | 4 | 5 | 4 | 4 |
| **Totale** | | **73.2** | **64.8** | **86.0** | **67.2** |

- **A, sicurezza 3:** oggi il pulsante avvia LLM e MT5 dalla dashboard. Esposta in LAN per il telefono, diventa una superficie di controllo.
- **B, sicurezza 2:** un'API richiede autenticazione e sessioni.
- **C, sicurezza 5:** niente server e niente input; la pagina si apre offline sul telefono e i grafici Plotly restano interattivi.
- **C, testabilità 5:** funzione pura archivio → HTML, verificabile con uno snapshot test.

**Raccomandazione: C.**
- La pagina mostra segnali, rischio, curve netta e lorda, calibrazione e confronti, e si rigenera a fine ciclo.
- Per il telefono: `http.server` su rete privata (per esempio Tailscale) o cartella sincronizzata.
- Contiene dati del conto: **niente hosting pubblico**.
- La skill `frontend-design` si applica qui, in Fase 6.

**Cosa farebbe cambiare idea:**
- l'utente vuole agire dal telefono → A con autenticazione e revisione di sicurezza;
- filtri interattivi su più di 10 mila righe → A in sola lettura.

---

## D10 — Esecuzione periodica

Alternative:
- **A. Ciclo `while`** con `sleep(900)`.
- **B. APScheduler.**
- **C. Utilità di pianificazione di Windows**, `main.py --once` ogni 15 minuti.
- **D. Ciclo allineato con la stdlib:** chiusura della prossima candela + 10-20 s, poi attesa della barra chiusa in MT5, con `run_once` idempotente.

| Criterio | Peso | A while | B APScheduler | C Pianificazione Windows | D Allineato |
|---|---|---|---|---|---|
| Correttezza | 20 | 2 | 4 | 4 | 5 |
| Misurabilità | 15 | 2 | 4 | 3 | 4 |
| Sicurezza operativa | 15 | 3 | 4 | 5 | 4 |
| Testabilità | 12 | 2 | 3 | 4 | 5 |
| Valore portfolio | 12 | 2 | 3 | 2 | 3 |
| Complessità | 10 | 5 | 3 | 4 | 4 |
| Tempo di sviluppo | 8 | 5 | 4 | 4 | 4 |
| Costo per segnale | 5 | 5 | 5 | 5 | 5 |
| Latenza | 3 | 3 | 5 | 3 | 5 |
| **Totale** | | **57.4** | **74.8** | **75.6** | **85.6** |

- **A, correttezza 2:** il ritardo si accumula, quindi la stessa candela può essere analizzata due volte o saltata.
- **D, testabilità 5:** `next_run` è una funzione pura con orologio iniettato, testabile con hypothesis.
- La chiusura della candela si legge dal timestamp della barra MT5, non dall'orologio locale.

**Raccomandazione: D**, con l'Utilità di pianificazione come supervisore (all'accesso e al riavvio dopo errore). Le due soluzioni si sommano.

Recupero dopo un crash:
1. si legge l'ultima candela elaborata nell'archivio;
2. si elabora solo l'ultima candela chiusa, se ha meno di 5 minuti;
3. le candele perse non si recuperano mai con l'LLM;
4. si risolvono gli esiti in sospeso;
5. se un ciclo supera 12 minuti, il successivo salta e lo registra.

**Cosa farebbe cambiare idea:**
- più di 2 calendari diversi → B;
- il demone muore più di una volta a settimana per perdite di memoria → C con un processo per ciclo.

---

## D11 — Configurazione

Alternative:
- **A. Dataclass attuale.**
- **B. pydantic-settings** con validazione all'avvio.
- **C. Dataclass validata**, solo stdlib.
- **D. TOML + env.**

| Criterio | Peso | A Dataclass | B pydantic-settings | C Dataclass validata | D TOML + env |
|---|---|---|---|---|---|
| Correttezza | 20 | 2 | 5 | 4 | 4 |
| Misurabilità | 15 | 3 | 4 | 4 | 4 |
| Sicurezza operativa | 15 | 2 | 5 | 4 | 4 |
| Testabilità | 12 | 2 | 5 | 5 | 4 |
| Valore portfolio | 12 | 2 | 4 | 3 | 3 |
| Complessità | 10 | 5 | 4 | 4 | 3 |
| Tempo di sviluppo | 8 | 5 | 4 | 4 | 3 |
| Costo per segnale | 5 | 5 | 5 | 5 | 5 |
| Latenza | 3 | 5 | 5 | 5 | 5 |
| **Totale** | | **58.6** | **91.0** | **81.6** | **75.6** |

- **A, correttezza 2:** valori fissati all'import, nessuna validazione (`RISK_PER_TRADE_PCT=50` passa), `ALLOW_LIVE_TRADING` assente.
- **A, sicurezza 2:** la `repr` espone i segreti.
- **B, sicurezza 5:**
  - `SecretStr` per chiavi e password;
  - validatore incrociato: ordini reali solo con `dry_run=False` e `allow_live_trading=True`, altrimenti errore all'avvio;
  - controllo degli intervalli sulle percentuali di rischio.
- **B, misurabilità 4:** `config_hash` senza segreti, salvato in `cycles`.

**Raccomandazione: B.** Una sola istanza costruita nella radice di composizione e passata come argomento, mai importata come globale nel dominio.

**Cosa farebbe cambiare idea:**
- divieto di dipendenze nuove → C;
- più di 15 parametri da versionare che cambiano spesso → D per quelli non segreti.

---

## D12 — LLM-as-a-judge

Alternative:
- **(a) Giudice decisore**, come oggi.
- **(b) Revisore con solo veto, in linea:**
  - schema chiuso `{veto, checks:[{id, passed, evidence}]}`;
  - verdetti alla cieca: etichette anonime, ordine casuale, niente confidenza dichiarata, niente dati del conto;
  - controlli deterministici spostati nel codice.
- **(c) Nessun giudice in linea:** il revisore gira offline in lotti sui candidati registrati e produce un **veto ombra** e un punteggio di qualità delle motivazioni.
- **(d) Revisore come caratteristica** nella logistica, senza veto.

| Criterio | Peso | (a) Decisore | (b) Veto in linea | (c) Offline / ombra | (d) Caratteristica |
|---|---|---|---|---|---|
| Correttezza | 20 | 2 | 4 | 4 | 4 |
| Misurabilità | 15 | 2 | 4 | 4 | 5 |
| Sicurezza operativa | 15 | 2 | 4 | 5 | 4 |
| Testabilità | 12 | 2 | 4 | 5 | 4 |
| Valore portfolio | 12 | 3 | 5 | 4 | 5 |
| Complessità | 10 | 4 | 3 | 4 | 3 |
| Tempo di sviluppo | 8 | 5 | 3 | 4 | 3 |
| Costo per segnale | 5 | 2 | 2 | 5 | 2 |
| Latenza | 3 | 2 | 2 | 5 | 2 |
| **Totale** | | **51.2** | **75.6** | **87.0** | **78.6** |

- **(a), correttezza 2:** rifà l'analisi, vede la confidenza dichiarata e i ruoli degli analisti, e decide livelli e lotto.
- **(b), sicurezza 4:** proprietà testabile: il veto può solo togliere operazioni, mai crearne. Formalmente `final_action(con veto) ∈ {final_action(senza veto), HOLD}`.
- **(c), costo e latenza 5:** non consuma tempo della finestra M15, e un giudice di famiglia diversa non costringe a cambi di modello durante il ciclo.

**Raccomandazione: (c), con promozione a (b) se i dati lo giustificano.** Si registrano veto ombra ed esito virtuale di tutti i candidati, vetati compresi, così l'ablation con/senza veto sugli stessi momenti non costa nulla.

### Modello del giudice (Q-001)

Alternative:
- **J1.** gemma3:12b, stessa famiglia degli analisti.
- **J2.** Qwen remoto.
- **J3.** Modello locale di altra famiglia, eseguito in lotti.

| Criterio | Peso | J1 gemma3:12b | J2 Qwen remoto | J3 Locale altra famiglia, in lotti |
|---|---|---|---|---|
| Correttezza | 20 | 2 | 4 | 4 |
| Misurabilità | 15 | 3 | 3 | 4 |
| Sicurezza operativa | 15 | 4 | 3 | 4 |
| Testabilità | 12 | 4 | 4 | 4 |
| Valore portfolio | 12 | 2 | 4 | 4 |
| Complessità | 10 | 5 | 4 | 3 |
| Tempo di sviluppo | 8 | 5 | 4 | 4 |
| Costo per segnale | 5 | 5 | 2 | 5 |
| Latenza | 3 | 4 | 4 | 4 |
| **Totale** | | **68.8** | **72.0** | **79.0** |

- **J1:** errori correlati con gli analisti e preferenza per i propri output (bias di auto-preferenza, Zheng et al. 2023).
- **J2:**
  - serve una versione fissa del modello, non un alias;
  - i dati escono dalla macchina, quindi niente capitale del conto nel prompt;
  - il costo va letto dal campo `usage` e salvato in `llm_calls.cost_eur`, senza stimarlo in anticipo.
- **J3:** modello di 7-14B non della famiglia gemma, in lotti quando il demone è inattivo. In linea costerebbe minuti di cambio di modello; offline il problema sparisce.

**Raccomandazione: J3 offline, più J2 su un campione** (per esempio il 20% dei candidati) per misurare l'accordo tra giudici.

### Metriche del giudice (preregistrate)

- **Precisione dei veti:** quota di vetati con R netto < 0, confrontata con quella dei non vetati. Si riportano lift con intervallo bootstrap e richiamo.
- **Ablation:** EV netto e Brier skill score con e senza veto, come differenza appaiata con intervallo bootstrap al 95%.
- **Stabilità:** temperatura 0 e seed fisso, 3 ripetizioni; stesso veto in almeno il 95% dei casi.
- **Bias di posizione:** si scambia l'ordine dei verdetti; il veto cambia in meno del 5% dei casi.
- **Bias di etichetta:** etichette anonime contro etichette con nome.
- **Accordo tra giudici:** kappa di Cohen J3-J2.
- **Valore predittivo delle motivazioni:** AUC del punteggio di qualità rispetto al TP; se l'intervallo include 0.5, nessun segnale.
- **Allucinazioni:** disaccordo con i controlli deterministici equivalenti.

**Cosa farebbe cambiare idea:**
- promozione a (b) solo con almeno 30 vetati e 100 candidati totali, e tutte queste condizioni:
  - lift > 1 con intervallo che esclude 1;
  - differenza di EV a favore del veto con intervallo che esclude 0;
  - stabilità ≥ 95%;
  - bias di posizione < 5%;
- kappa J3-J2 < 0.4 → la linea giudice si archivia;
- costo di J2 per 100 candidati sotto la soglia dell'utente → J2 al 100%.

---

## Coerenza tra le decisioni

1. **⚠ Blocco di avvio del gate EV: contraddizione nella specifica della Fase 4.**
   - Con β=0 vale p=p0 e, per costruzione, EV netto = −c/d_SL < 0. Quindi EV_5 ≤ EV < 0 = EV_MIN e **il gate non apre mai un trade**.
   - Ma β resta 0 finché non ci sono 100 trade chiusi: senza trade non si arriva mai a 100.
   - La Beta ha lo stesso problema con n=0.
   - **Soluzione proposta:** i "100 trade" sono **candidati risolti virtualmente** dal percorso del prezzo, eseguiti o no (`outcomes.resolved_by='virtuale'`).
   - Il sistema raccoglie dati senza operare, e opera solo quando il modello dimostra EV_5 > 0. È coerente con "nessun vantaggio dimostrato".
   - Con SL e TP a multipli fissi di ATR (per esempio 1 e 1.5), p0 è costante (0.4) e la Beta è ben definita.
   - **Serve la tua conferma (Q-004).**
2. **D2 + D3 + D4, candidati comuni:**
   - il generatore della baseline produce direzione e livelli;
   - le caratteristiche LLM sono covariate con segno;
   - tutte le varianti condividono gli stessi candidati, quindi il confronto è appaiato;
   - l'LLM si chiama solo sui cicli con un candidato, e questo riduce latenza e costo. Oggi 3 chiamate sequenziali per 6 simboli rischiano di superare la finestra M15 (stima, da misurare con `latency_ms`).
3. **D12 (c) + D3:** il veto ombra è una variante della Fase 5. Se promosso, agisce dopo il gate EV e può solo trasformare un trade in HOLD.
4. **"La confidenza LLM non entra mai":** va tolta dallo schema (D2), dal prompt del revisore (D12) e dall'ordinamento della dashboard (D9); `core/confidence.py` si elimina (D3).
5. **D8 + D2:** i β tecnici si possono pre-stimare sullo storico; i β LLM solo in avanti, con `model_digest` costante.
6. **D10 + D7 + D11:** `UNIQUE(symbol, candle_close_utc)` dà idempotenza; `config_hash` e `code_version` rendono ogni segnale riproducibile.
7. **D1 + D6 + guardrail:**
   - la porta broker è l'unico punto con `order_send`;
   - il validatore D11 sul doppio consenso è coperto da test;
   - D9 legge solo l'archivio, e questo elimina la seconda pipeline di `dashboard.py`.
8. **D5 + D4:** il macro si accende solo con notizie che hanno `fetched_at`; senza, la variante "solo macro" della Fase 5 viene riportata come non disponibile, non simulata.

### Varianti proposte per la Fase 5

Allineate al tuo elenco. Le stesse candele per tutte.

| # | Variante | Corrisponde a |
|---|---|---|
| 1 | Baseline p0 (nessun vantaggio) | baseline p0 |
| 2 | Baseline tecnica senza LLM (+ Beta / logistica su caratteristiche tecniche) | baseline tecnica |
| 3 | + caratteristiche LLM del tecnico | solo analista tecnico |
| 4 | + caratteristiche LLM del macro | solo macro |
| 5 | Regola di consenso tecnico/macro | consenso |
| 6 | Decisore LLM legacy (come oggi, per continuità con i 21 trade) | giudice LLM |
| 7 | Modello calibrato completo (± veto ombra) | modello calibrato |

---

## I 5 rischi principali dell'architettura raccomandata

1. **Potenza statistica insufficiente.** 100 candidati rilevano solo effetti di circa 12 punti sul tasso di TP. Il risultato probabile è "non concludente". Mitigazione: preregistrazione, intervalli sempre riportati, il risultato nullo dichiarato come risultato.
2. **Bias del simulatore di esiti virtuali:** ingresso alla chiusura, ambiguità dentro la candela, costo fisso, ora del server MT5 contro UTC. Potrebbe invalidare anche i 21 trade. Mitigazione: colonna `spread`, normalizzazione in UTC, riconciliazione con i fill demo.
3. **Sicurezza durante la transizione.** Finché `ALLOW_LIVE_TRADING`, la direzione TP/SL e il pip per coppia non sono corretti, il codice può inviare ordini con un solo flag e con livelli invertiti. Sono i primi passi della Fase 3.
4. **Le caratteristiche LLM potrebbero non avere informazione** (Brier 0.360 contro 0.250). L'architettura lo gestisce, ma il portfolio deve presentare la valutazione come prodotto principale.
5. **Una sola macchina Windows:** RAM e VRAM limitate, terminale MT5 da tenere connesso, sospensione, nuovi `pull` del modello. Il risultato sono buchi nella serie in avanti. Mitigazione: digest registrato, ripresa idempotente, supervisore, metrica di copertura in dashboard.

---

## Fonti (D5, D6)

Per lo più secondarie: i limiti vanno riconfermati sulle pagine ufficiali prima dell'implementazione.

- Finnhub: [API docs](https://www.finnhub.io/docs/api) · [apicostcalc](https://apicostcalc.com/finnhub.html) · [qveris, confronto API gratuite](https://qveris.ai/guides/free-financial-api-comparison)
- Marketaux: [freeapihub](https://freeapihub.com/apis/marketaux) · Alpha Vantage: [qveris](https://qveris.ai/guides/alpha-vantage-pricing-alternative/?lang=en)
- Calendario: [FMP pricing](https://site.financialmodelingprep.com/developer/docs/pricing) · [Trading Economics calendar API](https://tradingeconomics.com/calendar/api) · [FXMacroData vs Forex Factory](https://fxmacrodata.com/articles/fxmacrodata-vs-forex-factory)
- GDELT: [DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- Pepperstone: [piattaforme](https://pepperstone.com/en-au/platforms) · [cTrader](https://pepperstone.com/en/platforms/ctrader) · [algo trading](https://pepperstone.com/en-gb/platforms/tools/algorithmic-trading) · [demo](https://pepperstone.com/en-au/trading/demo-account) · [plugin cTrader PyneCore](https://github.com/PyneSys/pynecore-plugin-ctrader)
