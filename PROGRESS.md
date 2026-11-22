# PROGRESS
**Stato:** Fase 1 — Analisi delle alternative · **Aggiornato:** 2026-11-22 · **Prossima azione:** `/ecc:plan` con l'agente architect su D1–D12, output in `docs/ALTERNATIVE.md`.

## Piano
| # | Fase | Obiettivo | Criterio di uscita (verificabile) | Stato |
|---|------|-----------|-----------------------------------|-------|
| 0 | Lettura del contesto | Capire il sistema, creare CLAUDE.md/PROGRESS.md/DECISIONS.md | 30 test verdi; tre documenti presenti | fatto |
| 1 | Alternative (niente codice) | D1–D12 con matrici pesate e raccomandazioni | `docs/ALTERNATIVE.md` + un ADR per decisione; **approvazione utente** | in corso |
| 2 | Piano a fasi | Passi piccoli con test, file, accettazione, rischio | Piano in questo file; **approvazione utente** | da fare |
| 3 | Implementazione TDD | Dominio, porte, adattatori, orchestrazione, archivio | `pytest` verde; copertura dominio ≥ 85% | da fare |
| 4 | Modello di confidenza | p0, p*, EV, logistica walk-forward, gate EV_5 | Test obbligatori della specifica verdi | da fare |
| 5 | Valutazione | Test in avanti su demo; confronto delle 7 varianti | Report con BSS, EV e intervalli | da fare |
| 6 | Dashboard | Segnali, rischio, curve, calibrazione, confronti | Leggibile da telefono; ogni numero dall'archivio | da fare |
| 7 | Revisione e pubblicazione | Review, security scan, README onesto | `/code-review`, `/ecc:python-review`, `/ecc:security-scan` puliti | da fare |

## Dettaglio delle fasi
I passi della Fase 3 e successive vengono scritti qui in Fase 2, con l'agente planner.

## Log
- 2026-11-22: applicata la patch di sicurezza (commit `ab9c0b0` su main), creato il branch `ristrutturazione`. Fase 0 completata: 30 test verdi. Aggiunte le regole `permissions.deny` (verificate: il comando di prova viene bloccato).
