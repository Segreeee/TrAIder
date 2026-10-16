# TrAIder — MVP AI Trading Agent (LLM locali Ollama + MT5)

Demone headless che usa modelli locali Ollama (due analisti e un giudice)
come motore decisionale per generare segnali di trading, a partire da dati
OHLCV live da MetaTrader5 e notizie finanziarie reali (RSS Yahoo Finance).

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
│   ├── news_feed.py         # Data Ingestion notizie: RSS Yahoo Finance (sostituibile con Finnhub)
│   ├── prompt_builder.py    # Costruzione system/user prompt
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
   - i modelli Ollama (vedi sotto); `QWEN_*` non e' piu' usato dalla pipeline.
   - eventualmente `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` se il terminale
     non è già loggato manualmente.
   - Lascia `DRY_RUN=true` per i primi test: l'executor stampera' l'ordine
     simulato invece di inviarlo a MT5.
   - Modelli Ollama (default gia' impostati, tutti `gemma3:12b`):
     `OLLAMA_MODEL_TECHNICAL`, `OLLAMA_MODEL_MACRO` e `OLLAMA_MODEL_JUDGE`.
     Analista tecnico e macro emettono un verdetto ciascuno, il giudice
     arbitra (LLM-as-a-judge); se nessun analista risponde il giudice decide
     da solo. Usare lo stesso modello per tutti i ruoli evita i ricaricamenti
     (su 15 GB di RAM / 4 GB di VRAM ogni cambio modello costa minuti).
     Consigliato avviare Ollama con `OLLAMA_KEEP_ALIVE=30m` (o `-1`). Evita
     i modelli "thinking" (es. `deepseek-r1`) e quelli da 14B+ (`phi4`
     manda in crash il server per memoria su questa macchina).

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
   esegue un singolo ciclo (dati MT5 -> indicatori -> analisti + giudice -> risk check) e
   mostra il segnale con grafico a candele, RSI, motivazione del modello e
   storico delle analisi. La dashboard è puramente informativa: non invia mai
   ordini al conto, nemmeno in modalità live — l'eventuale esecuzione resta
   una decisione manuale dell'utente.

## Note di design

- **Risk management indipendente dall'LLM**: il `lot_size` proposto dall'LLM
  viene sempre validato/ricalcolato da `RiskManager.cap_llm_lot_size`, che
  applica il vincolo "rischio massimo 1% del capitale" in base alla distanza
  entry/stop-loss. L'LLM non ha mai l'ultima parola sul sizing.
- **Gestione errori**: timeout, errori HTTP e JSON malformati dal modello
  sollevano `QwenBrainError` e vengono loggati senza fermare il demone
  (il ciclo successivo riparte regolarmente).
- **Sostituibilità**: `YahooNewsFeed` implementa l'interfaccia astratta
  `NewsFeed.get_latest_news(symbol, limit)` — una futura `FinnhubNewsFeed`
  può sostituirla senza toccare `main.py` o `prompt_builder.py`.
- **Nessuna UI**: tutto l'output è su stdout + file di log rotante
  (`logs/traider.log`), adatto per essere eseguito come servizio/task
  schedulato.
