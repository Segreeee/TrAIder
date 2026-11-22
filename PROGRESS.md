# PROGRESS
**Stato:** Fase 2 — Piano a fasi · **Aggiornato:** 2026-11-22 · **Prossima azione:** piano dettagliato con l'agente planner, poi approvazione utente.

## Piano
| # | Fase | Obiettivo | Criterio di uscita (verificabile) | Stato |
|---|------|-----------|-----------------------------------|-------|
| 0 | Lettura del contesto | Capire il sistema, creare CLAUDE.md/PROGRESS.md/DECISIONS.md | 30 test verdi; tre documenti presenti | fatto |
| 1 | Alternative (niente codice) | D1–D12 con matrici pesate e raccomandazioni | `docs/ALTERNATIVE.md` + un ADR per decisione; **approvazione utente** | fatto |
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
- 2026-11-22: Fase 1 scritta: `docs/ALTERNATIVE.md` (D1–D12, matrici pesate) e ADR D-001…D-012 in stato Proposta. Trovati 2 problemi di sicurezza nuovi (T-006, T-007) e una contraddizione nella specifica della Fase 4 (Q-004).
- 2026-11-22: Fase 1 approvata dall'utente: D-001…D-012 accettate; Q-004 chiusa (candidati risolti virtualmente); fornitore del giudice remoto rimandato (Q-001).
