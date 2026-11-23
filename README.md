# TrAIder

Generatore di segnali forex su MetaTrader 5 che usa LLM locali (Ollama) come analisti, costruito per rispondere
a una domanda misurabile: **gli LLM migliorano la stima della probabilità di successo di un trade rispetto alla
sola analisi tecnica, dopo i costi?** Il sistema gira in simulazione (`DRY_RUN`) su sei coppie in M15 e registra
ogni decisione con il suo input completo, così la risposta si ottiene dai dati e non da un'impressione.

Stato: **raccolta dati in avanti in corso dal 23 novembre 2026**, secondo una
[preregistrazione](docs/PREREGISTRAZIONE.md) approvata prima di raccogliere i dati. Nessun risultato conclusivo
ancora: vedi [Risultati](#risultati).

## Come decide

Per ogni simbolo, a ogni chiusura di candela M15 ([diagramma del ciclo](docs/ciclo.html)):

1. **Candidato baseline.** Una regola tecnica fissa (EMA, trend H1, ATR) propone direzione, stop e target.
   Gli LLM non scelgono mai livelli né lotto.
2. **Analisti LLM come estrattori di caratteristiche.** Un analista tecnico (solo prezzi e indicatori) e uno
   macro (solo notizie) rispondono con uno schema chiuso `{direzione, forza, orizzonte, motivazioni}`, validato
   con pydantic, a temperatura 0. La confidenza dichiarata da un LLM non entra mai nel modello.
3. **Stima di p per variante.** Sullo stesso candidato si confrontano sei varianti, da `v1-p0` (solo geometria
   di stop e target) a `v7-completo` (tecnica + entrambi gli analisti). Prima di 100 esiti si usa una Beta
   centrata su p0, poi una logistica con offset, attivata solo se batte p0 fuori campione.
4. **Gate e rischio.** Si opera solo se EV_5 (valore atteso al 5° percentile di p, al netto dei costi) è
   positivo. Poi Kelly frazionato, rischio massimo 1% per trade, esposizione per valuta e limite di perdita
   giornaliera. Solo la variante di produzione arriva al broker, che è simulato.
5. **Esito virtuale.** Ogni candidato, eseguito o no, viene risolto sulle barre successive (TP, SL o scadenza
   dopo 24 h), in R netto e lordo.

## Architettura

Architettura esagonale leggera ([diagramma dei componenti](docs/architettura.html)): dominio puro (`domain/`,
senza I/O), cinque porte (`ports.py`: dati di mercato, notizie, LLM, broker, archivio) con un adattatore reale e
uno finto ciascuna, orchestrazione in `app/`, valutazione in `evaluation/`, dashboard statica in `report/`.
Le decisioni di progetto, con alternative e motivi, sono in [DECISIONS.md](DECISIONS.md) e
[docs/ALTERNATIVE.md](docs/ALTERNATIVE.md).

Sicurezza operativa, garantita da test:

- **Doppio consenso.** Il broker reale si costruisce solo con `DRY_RUN=false` **e** `ALLOW_LIVE_TRADING=true`;
  il costruttore del broker MT5 rifiuta comunque di partire senza consenso esplicito. Il default è simulato.
- **Nessun dato dal futuro.** Solo candele chiuse; le notizie entrano in un ciclo solo se erano già state
  scaricate prima della chiusura della candela.
- **Archivio a sola aggiunta.** Trigger SQLite contro modifiche e cancellazioni; ogni ciclo salva un input
  sufficiente a rifare candidato e decisioni (`app/replay.py`).
- **Regole di rischio con test a proprietà** (hypothesis): rischio entro il limite, lotto nullo o almeno
  minimo, mai due posizioni sullo stesso simbolo, esposizione per valuta limitata.

## Valutazione

- **Preregistrazione** ([docs/PREREGISTRAZIONE.md](docs/PREREGISTRAZIONE.md)): metrica primaria Brier skill
  score e R netto, `v7-completo` contro `v2-tecnica` sugli stessi candidati; bootstrap che ricampiona giorni
  interi (i candidati dello stesso giorno sono correlati), B = 2000, IC 95%; analisi finale con almeno 300
  candidati risolti e 30 giorni di mercato. Regole di decisione e limiti fissati prima dei dati.
- **Backtest** solo per le varianti senza LLM (`python -m evaluation.backtest`), walk-forward, con lo stesso
  simulatore di esito del demone. Le varianti con LLM si valutano solo in avanti, dopo la data di addestramento
  del modello.
- **Revisore giudice** offline e in ombra su un campione del 20%: non decide, misura se un veto avrebbe
  migliorato il risultato.

## Risultati

Riportati come sono, anche quando sono negativi.

- **Test in avanti:** in corso dal 23 novembre 2026. Nessun numero ancora significativo; la dashboard mostra
  l'avanzamento verso le soglie preregistrate.
- **Backtest di `v2-tecnica`** (EURUSD, 3000 barre M15 fino al 23 novembre 2026, 2047 candidati risolti):
  Brier skill score rispetto a p0 **−0.016**, IC 95% per giorno **[−0.036, 0.004]**; AUC 0.479. Su questo
  periodo le caratteristiche tecniche non mostrano valore predittivo rispetto alla sola geometria di stop e
  target. Il gate ha lasciato passare 20 trade, tutti nello stesso giorno, per −18.43 R netti. Un solo simbolo
  e poco più di un mese: un risultato descrittivo, non conclusivo.

## Uso

Requisiti: Windows con terminale MT5 su conto demo, Ollama in locale (`gemma3:12b`), Python 3.12.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env      (poi compilare: resta DRY_RUN=true)
.venv\Scripts\python main.py --once      # una sola candela
.venv\Scripts\python main.py             # demone, allineato alle candele M15
.venv\Scripts\python -m evaluation.report    # dall'inizio della preregistrazione; --tutto per un backtest
```

La dashboard (`DASHBOARD_PATH`) è una pagina HTML statica rigenerata a ogni candela, leggibile offline anche dal
telefono. Tutta la configurazione viene da variabili d'ambiente; nessun segreto nel codice o nei log.

Test e controlli (nessun test usa rete, MT5, Ollama o API a pagamento):

```
.venv\Scripts\python -m pytest
.venv\Scripts\python -m coverage run -m pytest && .venv\Scripts\python -m coverage report
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m mypy
```

## Limiti noti

- Simulatore: ingresso alla chiusura della candela con lo spread della barra, SL prioritario se TP e SL cadono
  nella stessa barra, nessuno slippage in uscita. Lo scarto rispetto ai fill reali si misura solo con ordini
  sul conto demo, che il progetto non invia senza una conferma esplicita.
- Notizie Finnhub generali sul forex (non per coppia), con una candela di ritardo; uso privato.
- Un solo modello locale per entrambi gli analisti (4 GB di VRAM).
- La potenza statistica è bassa: il risultato più probabile della preregistrazione è "non concludente", e
  verrà riportato così.
