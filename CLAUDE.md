# TrAIder
Generatore di segnali forex (MT5, Pepperstone, conto demo in EUR) con LLM locali (Ollama)
come analisti. Obiettivo: un sistema corretto, misurabile e sicuro, che dica con i dati se
esiste un vantaggio dopo i costi. Pezzo di portfolio AI Engineer: la valutazione conta quanto
la generazione.

## Stack e comandi
- Python 3.12, venv in `.venv` (Windows). Dipendenze: `requirements.txt` + `requirements-dev.txt`.
- Test: `.venv\Scripts\python -m pytest`
- Copertura: `.venv\Scripts\python -m coverage run -m pytest && .venv\Scripts\python -m coverage report`
- Demone (solo DRY_RUN): `python main.py` · Dashboard: `streamlit run dashboard.py`

## Workflow (obbligatorio, in ordine)
1. Leggi PROGRESS.md: fase corrente e prossima azione.
2. Per scelte di design consulta `~/.claude/playbooks/ingegneria-informatica/INDEX.md`.
3. Pianifica con `/ecc:plan` (agenti planner/architect); aspetta la conferma dell'utente.
4. Ogni modifica di codice con la skill `ecc:tdd-workflow`: test rosso, codice minimo verde, refactoring.
5. A fine fase: `/code-review`, `/ecc:python-review`, `ecc:verification-loop`.
6. Prima di ogni push: `/ecc:security-scan`. Push solo su conferma dell'utente.
7. Aggiorna PROGRESS.md a fine passo; proponi una voce in DECISIONS.md a ogni scelta.
8. Un commit per passo del piano, messaggio che spiega il perché.

## Regole di ingegneria
- Il dominio (tipi, costi, pip, probabilità, rischio, esposizione) è puro: niente I/O, niente MT5/LLM.
- Dati, notizie, LLM, broker e archivio stanno dietro porte; nei test solo adattatori finti.
- Ogni output LLM è validato da uno schema pydantic, temperatura 0, retry limitati,
  versione di modello e prompt registrata.
- La confidenza dichiarata dall'LLM non entra mai in decisioni né nel modello di probabilità.
- Valore del pip calcolato per coppia e valuta del conto (EUR), mai costanti fisse.
- Ogni segnale va nell'archivio con input completo, verdetti, p, p*, EV, decisione, esito, costi.
- Commenti e documenti in italiano; nomi coerenti con il modulo che si tocca.

## Guardrail
- MAI inviare ordini, nemmeno su demo, senza conferma esplicita dell'utente nella conversazione.
- MAI cambiare i default di sicurezza: `DRY_RUN=true`; ordini reali solo con
  `DRY_RUN=false` E `ALLOW_LIVE_TRADING=true`.
- MAI segreti nel codice, nei log o nei commit; configurazione solo da variabili d'ambiente.
- MAI test che usano rete, MT5, Ollama o API a pagamento.
- MAI cancellare log o dati dell'utente; per toglierli dall'indice `git rm --cached`.
- MAI modificare un test per farlo passare; MAI push o force-push senza chiedere.
- SEMPRE garantire le regole di rischio con test, inclusi test a proprietà (hypothesis):
  rischio ≤ limite; lotto = 0 oppure ≥ minimo; mai due posizioni sullo stesso simbolo;
  mai oltre l'esposizione per valuta.
- SEMPRE chiedere in caso di dubbio su soldi, ordini o rischio.
- SEMPRE riportare i risultati come sono, anche negativi.
- Le regole `permissions.deny` in `.claude/settings.json` bloccano i comandi con
  `DRY_RUN=false`, `ALLOW_LIVE_TRADING`, `order_send` e le modifiche a `.env`: non aggirarle.

## Definition of done
Test verdi e deterministici · copertura dominio ≥ 85% · review fatte · PROGRESS.md aggiornato.

## Mappa dei documenti
PROGRESS.md (stato, piano) · DECISIONS.md (ADR, domande aperte, TODO) ·
docs/ALTERNATIVE.md (matrici della Fase 1) · playbook al percorso sopra.
