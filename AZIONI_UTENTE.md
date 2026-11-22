# Azioni dell'utente

Cosa resta da fare a te, in ordine di urgenza. Aggiornato al 2026-11-22, dopo P3.27.
Dettagli di ogni voce in PROGRESS.md (passi P*) e DECISIONS.md (Q-*, T-*).

## 1. Decisioni che servono adesso

| Voce | Cosa decidere | Mia raccomandazione |
|---|---|---|
| **Q-005** | Soglia di attivazione del modello logistico. La regola "BSS > 0 fuori campione" si attiva per caso con caratteristiche senza informazione in 4 semi su 10. Opzioni: (a) estremo inferiore di un IC bootstrap al 90% del BSS > 0; (b) soglia fissa, es. BSS ≥ 0.01; (c) test contro β = 0 | (a) |
| **T-010** | Lo spread si conta due volte nei BUY (ingresso all'ask + spread dentro il costo c), circa 0.1 R a sfavore dei BUY; per i SELL l'uscita si controlla sul bid. Proposta: c senza spread quando le distanze partono dal prezzo di esecuzione, e uscite dei SELL controllate su bid + spread | correggere come proposto |
| **P3.18 / T-008** | Finnhub: i piani sono solo per uso personale e vietano di condividere dati **o risultati derivati** senza autorizzazione scritta. Opzioni: uso privato con solo metriche aggregate pubbliche; chiedere l'autorizzazione; saltare il passo (la variante "solo macro" risulta non disponibile) | autorizzazione scritta o saltare, se il progetto sarà pubblico |
| **Q-001** | Fornitore dell'API LLM remota per il giudice al 20%. Non blocca nulla: finché non scegli, solo giudice locale | — |

## 2. Prima di P3.28 (il nuovo programma legge la nuova configurazione)

1. **Aggiorna il tuo `.env`** (io non posso modificarlo):
   - togli `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_MODEL`, `SYMBOL`, `LOOP_INTERVAL_SECONDS`;
   - aggiungi `COMMISSION_EUR_PER_LOT=` con la commissione andata e ritorno per lotto standard del tuo conto demo Pepperstone (dalle specifiche del conto: Razor ha commissione, Standard di solito no). Senza, il costo stimato è solo spread + slippage;
   - facoltativi, con default prudenti: `MAX_LOT` (1.0), `MIN_LOT` e `LOT_STEP` (0.01), `PRODUCTION_VARIANT` (v7-completo). Modello: `.env.example`.
   - Dopo l'aggiornamento non lanciare il vecchio `main.py`: senza le righe `QWEN_*` ricadrebbe sull'indirizzo remoto predefinito di Qwen.
2. **P3.05 — fuso orario del server MT5**, a mercato aperto (lun–ven), terminale MT5 acceso:
   `.venv\Scripts\python tools\diagnose_mt5_tz.py`
   Mandami l'output: confermo l'offset e chiudo T-007. Lo script legge solo dati, nessun ordine.

## 3. Conferme durante le fasi successive

| Passo | Cosa ti chiederò |
|---|---|
| P3.29 | Migrazione dei 30 test legacy: conferma che `test_normal_case_unchanged` passa da 0.50 a 0.55 lotti (correzione del pip fisso) e il ritiro dei 2 test del giudice decisore |
| P3.31 | Cancellazione dei moduli legacy (`core/*`, `config/settings.py`, `backtest.py`) e dei vecchi test; restano recuperabili da git |
| P5.01 | Approvare la preregistrazione (metriche, soglie, varianti) **prima** di raccogliere dati |
| P5.08 | Scegliere il modello locale del giudice (famiglia diversa dagli analisti) e scaricarlo con `ollama pull` |
| P5.10 | Avviare tu il demone in DRY_RUN con il broker simulato e configurare l'Utilità di pianificazione come supervisore |
| P5.11 | **Ordini su conto demo:** imposti tu nel `.env` i due flag del doppio consenso e dai conferma esplicita in conversazione. Io non li tocco (e le regole deny lo impediscono) |
| P6.03 | Rimozione di Streamlit e di `dashboard.py`; accesso alla dashboard dal telefono (Tailscale o cartella sincronizzata) |

## 4. Prima della pubblicazione (Fase 7)

- **T-001:** conferma `git rm --cached` dei log (`logs/signals_history.json`, `logs/backtest_*.csv`); i file restano su disco.
- **T-003:** configura l'email "noreply" di GitHub per i commit (Settings → Emails → "Keep my email addresses private", poi `git config user.email <id>+<utente>@users.noreply.github.com`).
- **T-005:** decidi se versionare le regole `permissions.deny` (oggi `.claude/` è ignorata da git, quindi valgono solo su questa macchina).
- **T-002:** tenere o rimuovere `YahooNewsFeed` (oggi inutilizzata).
- **Push:** solo su tua conferma, dopo `/ecc:security-scan`.
