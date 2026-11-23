# Azioni dell'utente — guida passo passo

Aggiornata al 2026-11-22, dopo P3.27, Q-005 e T-010. Per ogni voce: **cosa**, **dove**, **come**, e cosa mandarmi alla fine.
Le voci sono in ordine: fai prima il blocco A, poi il B. I blocchi C e D arrivano più avanti, te li ricorderò io.

Legenda: 💬 = basta rispondermi in chat · 🖥️ = serve un'azione sul tuo PC · ✅ = fatto.

**Terminale:** in VS Code il terminale è Git Bash. Scrivi i percorsi con `/`, non con `\`
(Bash cancella le barre rovesciate: `.venv\Scripts\python` diventa `.venvScriptspython`).
Se il `.venv` è attivo (vedi `(.venv)` nel prompt) basta scrivere `python`.

---

## A. Adesso (sbloccano il lavoro)

### A1. ✅ Tre decisioni (fatto il 2026-11-22)

Hai scelto: **Q-005 → a** (già applicata), **T-010 → correggi** (già applicata), **Finnhub → uso privato** (sblocca P3.18, vedi B3).

<details><summary>Le domande originali</summary>


**Dove:** in questa chat. **Come:** una riga sola, per esempio:

> Q-005: a · T-010: correggi · Finnhub: salta

| Codice | La domanda in parole semplici | Opzioni | Consiglio |
|---|---|---|---|
| **Q-005** | Quando il modello statistico può "accendersi"? La regola attuale si accende per caso anche su dati senza informazione (4 volte su 10 nelle prove) | **a** = solo se anche la stima pessimistica (intervallo al 90%) è migliore della base · **b** = solo se migliora di almeno 0.01 · **c** = test statistico formale | **a** |
| **T-010** | Nei BUY lo spread viene contato due volte (≈ 0.1 R a sfavore dei BUY), nei SELL no | **correggi** = lo conto una volta sola per entrambi · **lascia** = resta prudente ma asimmetrico | **correggi** |
| **Finnhub** | I termini del piano gratuito vietano di condividere dati e "risultati derivati". Se pubblichi il progetto, i risultati dell'analista macro potrebbero rientrarci | **salta** = niente notizie, la variante "macro" risulta non disponibile · **privato** = uso solo personale, pubblichi solo metriche aggregate · **chiedo** = scrivi tu a Finnhub per un'autorizzazione | **salta** (o **chiedo** se vuoi il macro) |

</details>

Se scegli **chiedo** per Finnhub: vai su https://finnhub.io, usa il modulo/indirizzo di contatto indicato sul sito e chiedi il permesso di usare le notizie per un progetto di portfolio pubblico che mostra solo metriche aggregate. Dimmi poi la risposta.

### A2. ✅ Aggiorna il file `.env` (fatto: configurazione valida, verificata il 2026-11-22)

Io non posso modificarlo (le regole di sicurezza me lo impediscono), quindi lo fai tu.

**Dove:** in VS Code, nella cartella del progetto, apri il file `.env` (è nella radice, accanto a `main.py`; se non lo vedi nella barra a sinistra, premi `Ctrl+P` e scrivi `.env`).

**Come:**
1. **Cancella** queste 5 righe (seleziona la riga e premi `Ctrl+Shift+K`):
   ```
   QWEN_API_KEY=...
   QWEN_BASE_URL=...
   QWEN_MODEL=...
   SYMBOL=...
   LOOP_INTERVAL_SECONDS=...
   ```
   Le altre righe che hai già (`MT5_*`, `SYMBOLS`, `TIMEFRAME`, `CANDLES_COUNT`, `ACCOUNT_BALANCE`, `RISK_PER_TRADE_PCT`, `DRY_RUN`) sono già valide: lasciale.
2. **Aggiungi** in fondo questa riga, con il numero giusto per il tuo conto (vedi A3):
   ```
   COMMISSION_EUR_PER_LOT=
   ```
3. Salva con `Ctrl+S`.

**Verifica (facoltativa):** nel terminale di VS Code (menu **Terminale → Nuovo terminale**) incolla:
```
python -c "from app.config import Settings; Settings(); print('configurazione valida')"
```
Se stampa `configurazione valida` hai finito. Se stampa un errore, copiamelo: contiene solo i nomi dei campi, non i valori, ma controlla comunque prima di incollarlo.

⚠️ Dopo questa modifica **non lanciare il vecchio `python main.py`**: senza le righe `QWEN_*` userebbe l'indirizzo remoto predefinito di Qwen. Il nuovo avvio arriva con P3.28.

### A3. ✅ Trova la commissione del tuo conto demo (fatto)

**Cosa serve:** la commissione **andata e ritorno** per **1 lotto standard**, in **EUR**.

**Dove guardare:**
1. **Area clienti Pepperstone** (sito o app): nei dettagli del conto demo trovi il **tipo di conto**.
   - **Standard**: di solito nessuna commissione → scrivi `COMMISSION_EUR_PER_LOT=0`.
   - **Razor**: c'è una commissione per lotto → prendi il valore dalla pagina dei tipi di conto/costi di Pepperstone per i conti in EUR.
2. Attenzione a come è espressa: se il sito la indica **per lato** (solo apertura), **raddoppiala** per avere andata e ritorno.
3. Basta il valore del sito: il costo reale lo verificheremo più avanti, in P5.11, solo se deciderai di operare sul demo.

Se non sei sicuro del valore, scrivimi tipo di conto e cosa vedi sul sito, e lo ricaviamo insieme. Non lo invento io.

### A4a. 🖥️ Cambia la password del conto demo e controlla il server (urgente)

Durante un test la password MT5 del `.env` è finita in un messaggio di errore (difetto dei test, ora corretto:
nessun test può più leggere la configurazione reale). Per sicurezza:
1. **Cambia la password del conto demo** (in MT5: *Strumenti → Opzioni → Server → Cambia*, oppure dall'area clienti del broker) e aggiorna `MT5_PASSWORD` nel `.env`.
2. **Controlla il server:** nel `.env` `MT5_SERVER` indica un server **MetaQuotes**, non Pepperstone. Il progetto prevede il demo **Pepperstone in EUR**. In MT5 apri *File → Accedi al conto di trading*: lì vedi numero di conto e nome esatto del server (per Pepperstone è del tipo `Pepperstone-Demo`). Metti nel `.env` `MT5_LOGIN` e `MT5_SERVER` del conto Pepperstone. I conti demo MetaQuotes scadono dopo un periodo di inattività: è una causa probabile dell'errore -6.

### A4. ✅ Verifica il fuso orario del server MT5 (P3.05) — chiusa il 2026-11-22 (+2 ore)

Risultato del 2026-11-22: **+2 ore**, ma su un server **MetaQuotes**. Dopo aver messo nel `.env` il conto demo Pepperstone (A4a), rilancia lo stesso comando e mandami di nuovo le tre righe.

*Chiusa su tua decisione: il `.env` è quello voluto. Il testo qui sotto resta come riferimento.*


**Quando:** da **lunedì a venerdì**, con il mercato aperto. Oggi è domenica: il forex riapre domenica sera (ora italiana circa 23:00), ma meglio lunedì in orario europeo.

**Dove:** sul PC dove gira MetaTrader 5.

**Come:**
1. Apri **MetaTrader 5** (quello di Pepperstone). Lo script ora usa login, password e server del `.env`, quindi basta che il terminale sia installato; se è aperto, verifica che in basso a destra non ci sia "Nessuna connessione".
2. In VS Code apri il terminale: menu **Terminale → Nuovo terminale**.
3. Incolla ed esegui:
   ```
   python tools/diagnose_mt5_tz.py
   ```
4. Vedrai tre righe come queste:
   ```
   UTC adesso:               2026-11-23T09:07:12+00:00
   Apertura barra (server):  2026-11-23 11:00:00
   Scarto server - UTC:      +2 ore
   ```
5. **Mandami le tre righe** in chat.

Lo script **legge solo dati**: non apre posizioni e non usa funzioni di trading.
Se compare "Scarto non determinabile", il mercato è chiuso: riprova più tardi in un giorno feriale.
Se compare "initialize fallita: (-6, ...Authorization failed)", login, password o server del `.env` non corrispondono al conto (vedi A4a).

### A5. 🖥️ Primo avvio di prova del nuovo programma (una sola candela)

**Cosa fa:** elabora l'ultima candela chiusa per i 6 simboli e si ferma. Broker **simulato**: nessun ordine
(verificato: con il tuo `.env` DRY_RUN è attivo e il secondo consenso è spento). Scrive in `data/traider.db` e in `logs/traider.log`.

**Prima:**
1. **MetaTrader 5** installato (lo script usa le credenziali del `.env`).
2. **Ollama** acceso, con il modello degli analisti scaricato. Nel terminale:
   ```
   ollama list
   ```
   Deve comparire `gemma3:12b`. Se manca: `ollama pull gemma3:12b`.
3. Mercato aperto (da domenica sera a venerdì sera).

**Come:** nel terminale di VS Code, dalla cartella del progetto:
```
python main.py --once
```
Ci vorrà qualche minuto (fino a 12 chiamate LLM). **Mandami le ultime 20-30 righe** dell'output, oppure
il contenuto di `logs/traider.log`. Controlla prima che non ci siano chiavi o password (non dovrebbero esserci).

Se compare `configurazione non valida: ...` o `MetaTrader5 non inizializzato`, mandami quella riga.

---

## B. Quando vuoi (non bloccano nulla)

### B1. 💬 Fornitore LLM remoto per il giudice (Q-001)
Quando avrai scelto un servizio (per esempio uno compatibile con l'API OpenAI), dimmi quale. Ti dirò quali 3 righe aggiungere al `.env` (`REMOTE_JUDGE_BASE_URL`, `REMOTE_JUDGE_MODEL`, `REMOTE_JUDGE_API_KEY`). La chiave la inserisci solo tu nel `.env`, mai in chat.

### B2. 💬 Due scelte di pulizia
- **T-002:** tenere o eliminare `YahooNewsFeed` (codice vecchio, oggi inutilizzato). Consiglio: eliminare.
- **T-005:** le regole di sicurezza (`.claude/settings.json`) oggi valgono solo su questo PC perché la cartella `.claude/` non è nel repository. Vuoi che le versioniamo? Consiglio: sì, sono una garanzia visibile anche nel portfolio.

---

### B3. 🖥️ Chiave Finnhub (l'adattatore è pronto: puoi farlo ora)
Hai scelto l'uso privato. L'adattatore è pronto (P3.18); le notizie si accendono quando il nuovo programma parte (P3.28). Passi:
1. registrarti su https://finnhub.io (piano gratuito) e copiare la **API key** dalla dashboard;
2. aggiungere nel `.env` le righe `NEWS_PROVIDER=finnhub` e `FINNHUB_API_KEY=<la tua chiave>`.
La chiave va solo nel `.env`, mai in chat. Promemoria della scelta: i titoli delle notizie restano in `data/`
(ignorata da git) e in pubblico mostrerai solo metriche aggregate.

---

## C. Più avanti: te lo chiederò io al momento giusto

Non devi fare nulla ora. Quando arriviamo al passo, ti scrivo la domanda precisa e tu rispondi in chat.

| Passo | Cosa ti chiederò | Tipo |
|---|---|---|
| P3.29 | ✅ Fatto (conferme date all'approvazione del piano) | — |
| P3.31 | ✅ Fatto il 2026-11-23: codice vecchio cancellato su tua conferma (recuperabile da git) | — |
| P5.01 | ✅ Fatto il 2026-11-23: preregistrazione approvata (commit 8d8b8c2, 16:41 UTC) | — |
| P5.08 | Codice pronto (D-018: giudice su API esterna). Quando scegli il fornitore (B1) si lancia a mano: `.venv\Scripts\python -m evaluation.judge_batch`. Ogni lancio costa: 5 chiamate per ciclo giudicato, sul 20% dei cicli | 🖥️ |
| P5.10 | Pronto: istruzioni nella sezione E qui sotto | 🖥️ |
| P5.11 | **Ordini sul conto demo:** solo se e quando lo decidi tu. Imposti tu nel `.env` i due flag del doppio consenso e me lo confermi in chat. Io non li tocco mai | 🖥️ + 💬 |
| P6.03 | Confermare la rimozione della vecchia dashboard Streamlit e scegliere come vedere la nuova dal telefono (Tailscale o cartella sincronizzata) | 💬 |

---

## E. 🖥️ P5.10 — Avviare il test in avanti (DRY_RUN, broker simulato)

La preregistrazione è approvata: da adesso ogni ciclo conta. Il programma resta in simulazione (nessun ordine).

1. **Market Watch di MT5:** aggiungi in modo permanente EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF e le
   coppie di conversione EURJPY, EURCAD, EURCHF (tasto destro nel Market Watch → Simboli). Così le quotazioni
   arrivano sempre e i cicli non finiscono in "candela non ancora disponibile".
2. **Il PC non deve andare in sospensione:** Impostazioni → Sistema → Alimentazione → sospensione "Mai"
   quando è collegato alla corrente. MT5 e Ollama devono restare aperti.
3. **Supervisore (Utilità di pianificazione):** "Crea attività" (non "attività di base"):
   - *Generale:* nome `TrAIder`, "Esegui solo se l'utente è connesso" (serve il terminale MT5 aperto).
   - *Attivazione:* "All'accesso", poi "Ripeti attività ogni **15 minuti**" per "**Illimitatamente**".
   - *Azione:* programma `C:\Users\39342\Desktop\TrAIder\.venv\Scripts\python.exe`,
     argomenti `main.py`, "Inizia in" `C:\Users\39342\Desktop\TrAIder`.
   - *Impostazioni:* "Se l'attività è già in esecuzione: **Non avviare una nuova istanza**"; togli
     "Interrompi l'attività se viene eseguita per più di…".

   Se il programma si ferma (errore, riavvio del PC) riparte entro 15 minuti. Le candele perse non si
   recuperano (D-010): il report le conta nella copertura.
4. **Nessuna modifica in corsa (§7):** durante la raccolta non cambiare `.env`, simboli, modello Ollama né
   codice. Se devi farlo, dimmelo prima: si apre una nuova serie.
5. **Controllo:** `logs/traider.log` ha una riga per simbolo a ogni candela. Il report si legge quando vuoi,
   solo sui cicli dopo l'approvazione:
   `.venv\Scripts\python -m evaluation.report --dal 2026-11-23T16:45:00+00:00`
   A 100 candidati risolti facciamo insieme l'analisi intermedia (solo descrittiva).

---

## D. Prima di pubblicare su GitHub (Fase 7)

### D1. 🖥️ Email "noreply" per i commit (T-003)
Serve a non pubblicare la tua email personale nei commit.
1. Vai su **github.com → foto profilo in alto a destra → Settings → Emails**.
2. Spunta **"Keep my email addresses private"**.
3. Copia l'indirizzo mostrato, del tipo `12345678+nomeutente@users.noreply.github.com`.
4. Nel terminale di VS Code, nella cartella del progetto:
   ```
   git config user.email "12345678+nomeutente@users.noreply.github.com"
   ```
   (con il tuo indirizzo). Vale solo per questo progetto.

### D2. 💬 Togliere i log dall'indice (T-001)
Ti chiederò conferma per `git rm --cached` dei file in `logs/`: smettono di essere tracciati da git ma **restano sul tuo disco**.

### D3. 💬 Push
Dopo il controllo di sicurezza (`/ecc:security-scan`) ti chiederò se pubblicare. Senza il tuo "sì" non faccio nessun push.
