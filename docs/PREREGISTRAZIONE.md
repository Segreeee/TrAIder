# Preregistrazione della valutazione in avanti (Fase 5)

**Stato:** APPROVATA dall'utente il 2026-11-23. Questo commit è la marca temporale: i dati analizzati sono quelli raccolti dopo.
**Domanda:** gli LLM locali, usati come estrattori di caratteristiche (D-002), migliorano la stima della probabilità di TP e il risultato netto rispetto alla sola analisi tecnica, dopo i costi?

## 1. Disegno

- **Raccolta in avanti**, in DRY_RUN con il broker simulato (D-006, D-008). Tutto ciò che usa un LLM si valuta solo in avanti, dopo la data di addestramento del modello, con `model_digest` registrato.
- **Unità di analisi:** il candidato, cioè una coppia (simbolo, candela M15 chiusa) che il generatore baseline propone. Tutte le varianti stimano p **sullo stesso candidato**, quindi i confronti sono appaiati.
- **Esito:** risoluzione virtuale di ogni candidato, eseguito o no (Q-004): primo tra TP e SL su barre successive alla chiusura (SL se nella stessa barra), TIMEOUT dopo 96 barre (24 h). R netto con il costo registrato alla decisione.
- **Simboli e timeframe:** EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF; M15 con trend H1.
- **Inizio:** il primo ciclo dopo il commit di approvazione. **Fine:** al raggiungimento delle soglie della §5 oppure il 2027-03-07, la prima delle due (prima del cambio di ora legale del server, T-011).

## 2. Varianti confrontate

Stesse candele, stesso candidato, stima di p diversa (`app/variants.py`):

| Variante | Caratteristiche | Disponibile |
|---|---|---|
| `v1-p0` | nessuna: p = p0 = d_SL / (d_SL + d_TP) | sempre |
| `v2-tecnica` | momentum, scarto RSI, istogramma MACD / ATR | sempre |
| `v3-llm-tecnico` | tecniche + analista tecnico LLM | se il tecnico è stato chiamato |
| `v4-llm-macro` | tecniche + analista macro LLM | solo con notizie visibili |
| `v5-consenso` | tecniche, solo se tecnico e macro concordano col candidato | solo con notizie visibili |
| `v7-completo` | tecniche + tecnico + macro (variante di produzione) | sempre (macro assente = 0) |

La variante 6 (decisore legacy in ombra) è esclusa (D-017): una terza chiamata LLM per candidato e un ruolo, l'LLM decisore, che D-002 ha già scartato. Le varianti 4 e 5 si confrontano solo sui candidati in cui erano disponibili; quante volte lo sono è riportato.

## 3. Modello di probabilità (fissato)

- Beta(κ·p0 + TP, κ·(1 − p0) + SL) con κ = 20; i TIMEOUT non contano.
- Logistica con offset logit(p0) quando ci sono almeno **100 candidati** risolti (TP o SL) della variante **e** l'estremo inferiore dell'IC bootstrap al 90% del Brier skill score fuori campione (ultimo 30% in ordine di tempo) è > 0 (Q-005). p5 da bootstrap; se l'ottimizzatore non converge si usa la Beta.
- Gate: EV_5 > EV_MIN = 0, poi rischio ed esposizione; Kelly frazionato λ = 0.25, rischio massimo 1% per trade.
- La confidenza dichiarata dagli LLM non entra in nessuna stima.

## 4. Metriche

### Primarie (confronto `v7-completo` contro `v2-tecnica`)
1. **Brier skill score** rispetto a p0, su candidati con esito TP o SL (y = 1 se TP): BSS = 1 − Brier(variante) / Brier(p0). Statistica: ΔBSS = BSS(v7) − BSS(v2), appaiato.
2. **R netto** medio per candidato **deciso TRADE** dalla variante (decisione virtuale, anche se non eseguita), TIMEOUT inclusi. Statistica: differenza tra v7 e v2; si riporta anche il numero di candidati TRADE di ciascuna.

### Secondarie (riportate tutte, nessuna decide da sola)
- BSS di ogni variante rispetto a p0 e a `v2-tecnica`; log-loss; calibrazione per decili (affidabilità); AUC.
- R lordo e netto totali; EV previsto contro realizzato; max drawdown in R della variante di produzione.
- Copertura: candele attese, cicli completati, cicli in errore e motivo, candidati senza esito.
- Output LLM non validi per ruolo (soglia D-002: 5%).
- Esplorative, per simbolo e per sessione (Asia, Londra, New York): solo descrittive.

### Revisore giudice (D-012, offline, in ombra)
Metriche: precisione dei veti e lift con IC, richiamo; ablation (ΔEV e ΔBSS appaiati con IC); stabilità su 3 ripetizioni; bias di posizione e di etichetta; kappa tra giudice locale e remoto (se Q-001 è decisa); AUC delle motivazioni; allucinazioni. Promozione a veto in linea solo con: almeno 30 veti su almeno 100 candidati, lift con IC che esclude 1, ΔEV con IC che esclude 0, stabilità ≥ 95%, bias di posizione < 5%. Kappa < 0.4: linea del giudice archiviata.

## 5. Inferenza e soglie

- **Dipendenza:** candidati consecutivi dello stesso simbolo condividono gran parte dell'orizzonte di 24 h e non sono indipendenti. Il bootstrap ricampiona **per giorno** (UTC), non per candidato.
- **Bootstrap:** appaiato, B = 2000, seme 20261123, IC 95% percentile.
- **Analisi intermedia a 100 candidati** risolti di `v2-tecnica`: solo descrittiva, più le verifiche di D-002 e D-003. Non si ferma la raccolta per efficacia.
- **Analisi finale:** almeno 300 candidati risolti (TP o SL) di `v2-tecnica` **e** almeno 30 giorni di mercato con dati; oppure alla data di fine della §1.

## 6. Regole di decisione (fissate ora)

- **Gli LLM aggiungono valore** se l'IC 95% di ΔBSS(v7 − v2) è tutto sopra 0 **e** quello della differenza di R netto non è tutto sotto 0.
- **Gli LLM peggiorano** se l'IC di ΔBSS è tutto sotto 0.
- Altrimenti il risultato è **non concludente** e si riporta così, con gli intervalli. Con questa potenza è l'esito più probabile.
- **D-002:** dopo 100 candidati, se il coefficiente LLM ha IC che include 0 e il BSS ≤ 0, gli LLM passano a "solo spiegazione".
- **D-003:** se il BSS della variante di produzione contro baseline + p0 è ≤ 0 fuori campione, in produzione resta la baseline.
- Nessuna soglia di questo documento si sposta dopo aver visto i dati.

## 7. Nessuna modifica in corsa

Regola: nessuna modifica in corsa. Durante la raccolta non cambiano codice di decisione, prompt (versione registrata), modello (`model_digest`), configurazione (`config_hash`) né simboli. Se un cambio è inevitabile (difetto, guasto), si registra la data, si apre una nuova serie e le serie si analizzano separatamente per `config_hash`, versione dei prompt e `model_digest`. Le correzioni che non toccano la decisione (log, dashboard, report) non aprono una nuova serie.

## 8. Esclusioni (decise ora)

- Cicli in errore: esclusi dalle metriche, contati nella copertura con il motivo.
- Candidati senza esito alla fine: esclusi e contati.
- Candele perse (demone fermo, MT5 non aggiornato): mai recuperate con l'LLM (D-010), contate nella copertura.

## 9. Limiti noti (dichiarati prima)

- Simulatore: ingresso al prezzo di chiusura con lo spread della barra, SL prioritario a parità di barra, nessuno slippage in uscita. Il confronto con i fill sul conto demo (P5.11, D-014) misura lo scarto; oltre 0.1 R serve una nuova ADR.
- Notizie con una candela di ritardo (D-015); Finnhub restituisce notizie forex generali, non per coppia.
- Costo = commissione configurata + slippage 0.2 pip; lo spread è già nel prezzo d'ingresso (T-010).
- Ora legale del server non gestita per barre precedenti al cambio (T-011): da qui la data di fine.
- Un solo modello locale (gemma3:12b) per tecnico e macro (D-004).
- Con il gate chiuso (p = p0 finché la Beta non si sposta) i trade eseguiti in simulazione saranno pochi: la metrica primaria 2 usa le decisioni virtuali di ogni variante.
