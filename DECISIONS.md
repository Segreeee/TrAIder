# DECISIONS
ADR brevi, uno per decisione. Le decisioni accettate non si modificano: si sostituiscono con una nuova voce.
Le analisi complete con le matrici stanno in `docs/ALTERNATIVE.md`.

## Decisioni
_Nessuna decisione accettata. Gli ADR D1–D12 vengono proposti in Fase 1 e accettati dall'utente._

<!-- Modello:
### D-001 — <titolo>  ·  Stato: Proposta | Accettata | Sostituita da D-00X  ·  <data>
- **Contesto:** …
- **Alternative:** A … / B … / C …
- **Decisione e motivo:** …
- **Conseguenze / compromessi:** …
- **Cosa farebbe cambiare idea:** …
- **Riferimento playbook:** ~/.claude/playbooks/ingegneria-informatica/…
-->

## Domande aperte
- Q-001 — Modello del giudice: Qwen remoto, locale di altra famiglia o gemma3:12b. Decisione rimandata a D12 con i costi reali (blocca: Fase 2).
- Q-002 — Ruolo del giudice: decisore, revisore con veto, o assente (blocca: D3/D12).

## TODO
| ID | Voce | Responsabile | Collegato a | Stato |
|----|------|--------------|-------------|-------|
| T-001 | `git rm --cached` di `logs/signals_history.json` e `logs/backtest_*.csv` (restano su disco) | claude, su conferma | Fase 7 | da fare |
| T-002 | `YahooNewsFeed` non usata dopo la patch: decidere se rimuoverla o tenerla come adattatore | utente | D5 | da fare |
| T-003 | Ricordare all'utente di configurare l'email "noreply" di GitHub per i commit | claude | Fase 7 | da fare |
| T-004 | Controllo della direzione di TP/SL mancante (`abs()` nel calcolo di R:R) | claude | Fase 3, dominio | da fare |
| T-005 | `.claude/` è in `.gitignore`: le regole deny valgono solo su questa macchina | utente | Guardrail | da decidere |
