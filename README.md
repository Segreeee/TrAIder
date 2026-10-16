# TrAIder — MVP AI Trading Agent (Qwen + MT5)

Demone headless che usa Qwen (via API OpenAI-compatible) come motore
decisionale per generare segnali di trading su EURUSD, a partire da dati
OHLCV live da MetaTrader5 e notizie finanziarie (mock).

## Albero del progetto

```
TrAIder/
├── main.py                 # Entry point demone headless: loop continuo automatico
├── dashboard.py             # Entry point GUI (Streamlit): analisi on-demand a bottone
├── requirements.txt
├── .env.example             # Template variabili d'ambiente (copiare in .env)
├── config/
│   ├── __init__.py
│   └── settings.py          # Configurazione centralizzata (letta da .env)
├── core/
│   ├── __init__.py
│   ├── data_feed.py         # Data Ingestion mercato: MT5 + RSI/EMA (pandas-ta)
│   ├── news_feed.py         # Data Ingestion notizie: mock-up (sostituibile con Finnhub)
│   ├── prompt_builder.py    # Costruzione system/user prompt per Qwen
│   ├── qwen_brain.py        # Chiamata LLM (openai SDK) + parsing/validazione JSON
│   ├── risk_manager.py      # Calcolo lot size max (rischio 1% capitale)
│   └── executor.py          # Esecuzione ordine: mock (dry-run) o invio reale a MT5 (solo main.py)
└── logs/
    ├── traider.log           # Log rotante generato da main.py
    └── signals_history.json  # Storico segnali generati dalla dashboard
```

## Setup

1. Crea un virtual environment e installa le dipendenze:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   Nota: `MetaTrader5` richiede Windows con il terminale MT5 installato e
   loggato (o credenziali valide in `.env`). `pandas-ta` viene usato al posto
   di TA-Lib per evitare la compilazione di dipendenze C.

2. Copia `.env.example` in `.env` e compila almeno:
   - `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_MODEL`
   - eventualmente `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` se il terminale
     non è già loggato manualmente.
   - Lascia `DRY_RUN=true` per i primi test: l'executor stampera' l'ordine
     simulato invece di inviarlo a MT5.

3. Avvia il demone headless (loop automatico, esegue/simula ordini):
   ```
   python main.py
   ```
   Il ciclo (fetch dati -> LLM -> risk check -> esecuzione) gira ogni
   `LOOP_INTERVAL_SECONDS` (default 900s = 15 minuti, coerente col timeframe M15).

   Oppure avvia la dashboard grafica (analisi manuale a richiesta, nessun ordine automatico):
   ```
   streamlit run dashboard.py
   ```
   Si apre nel browser su `http://localhost:8501`. Premendo **"Analizza ora"**
   esegue un singolo ciclo (dati MT5 -> indicatori -> Qwen -> risk check) e
   mostra il segnale con grafico a candele, RSI, motivazione del modello e
   storico delle analisi. La dashboard è puramente informativa: non invia mai
   ordini al conto, nemmeno in modalità live — l'eventuale esecuzione resta
   una decisione manuale dell'utente.

## Note di design

- **Risk management indipendente dall'LLM**: il `lot_size` proposto da Qwen
  viene sempre validato/ricalcolato da `RiskManager.cap_llm_lot_size`, che
  applica il vincolo "rischio massimo 1% del capitale" in base alla distanza
  entry/stop-loss. L'LLM non ha mai l'ultima parola sul sizing.
- **Gestione errori**: timeout, errori HTTP e JSON malformati dal provider
  Qwen sollevano `QwenBrainError` e vengono loggati senza fermare il demone
  (il ciclo successivo riparte regolarmente).
- **Sostituibilità**: `MockNewsFeed` implementa l'interfaccia astratta
  `NewsFeed.get_latest_news(symbol, limit)` — una futura `FinnhubNewsFeed`
  può sostituirla senza toccare `main.py` o `prompt_builder.py`.
- **Nessuna UI**: tutto l'output è su stdout + file di log rotante
  (`logs/traider.log`), adatto per essere eseguito come servizio/task
  schedulato.
