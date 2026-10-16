"""
Prompt Builder.

Assembla in un unico prompt testuale:
- payload OHLCV compatto (JSON minimale),
- indicatori tecnici correnti,
- notizie finanziarie recenti,
- parametri di rischio/conto,
cosi' che il modello Qwen abbia tutto il contesto necessario per decidere.
"""
import json
from typing import List, Optional

from core.news_feed import NewsItem

SYSTEM_PROMPT = """Sei un prop-trader algoritmico istituzionale specializzato in Forex, \
con anni di esperienza in risk management sistematico e analisi tecnica intraday. \
Operi con disciplina rigorosa: non ti innamori mai di una posizione, tagli le perdite \
in fretta e rispetti sempre i limiti di rischio imposti dal desk.

Regole vincolanti:
1. Analizza esclusivamente i dati di mercato (OHLCV, indicatori, trend multi-timeframe) e le \
notizie fornite.
2. Se il segnale non e' sufficientemente chiaro, se il rischio/rendimento non e' favorevole, o \
se il timeframe operativo (M15) e' in chiaro disallineamento col trend di fondo (timeframe \
superiore), rispondi con action "HOLD".
3. take_profit_price e stop_loss_price devono essere coerenti con la direzione del trade \
(per un BUY: stop_loss < prezzo corrente < take_profit; per un SELL l'inverso) e con un \
rapporto rischio/rendimento di almeno 1:1.5. Usa l'ATR corrente come riferimento per una \
distanza di stop loss realistica rispetto alla volatilita' attuale (evita stop troppo stretti \
in mercati volatili o troppo larghi in mercati piatti).
4. lot_size deve essere la tua proposta di dimensionamento, ma verra' comunque validata e \
ricalcolata da un modulo di risk management esterno che applica un limite massimo di rischio \
per trade sul capitale del conto: proponi un valore prudente e coerente con quel vincolo.
5. Rispondi SEMPRE e SOLO con un oggetto JSON puro, nessun testo aggiuntivo, nessun markdown, \
nessuna spiegazione fuori dal campo "reasoning".

Formato di risposta obbligatorio (JSON puro):
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence_percentage": <int 0-100>,
  "lot_size": <float>,
  "take_profit_price": <float>,
  "stop_loss_price": <float>,
  "reasoning": "<string breve, max 3 frasi>"
}
"""

REASONING_SYSTEM_PROMPT = """Sei lo stesso prop-trader algoritmico istituzionale descritto sopra, \
ma in questa fase NON devi ancora emettere un verdetto: devi solo ragionare ad alta voce, in \
prosa libera (nessun JSON, nessun formato rigido), sui dati di mercato, gli indicatori tecnici, \
l'allineamento tra timeframe M15 e il trend di fondo, e le notizie fornite.

Struttura il tuo ragionamento toccando esplicitamente:
- Il momentum e la struttura di prezzo su M15 (pattern, supporti/resistenze recenti).
- Cosa suggeriscono RSI, MACD e Bollinger Bands, e se sono in accordo o in conflitto tra loro.
- Se il trend sul timeframe superiore conferma o contraddice un eventuale movimento su M15.
- L'impatto plausibile delle notizie fornite sul sentiment dell'asset.
- I livelli di prezzo piu' sensati per un eventuale stop loss e take profit, con riferimento \
all'ATR corrente.

Sii concreto e quantitativo (cita i valori numerici forniti), ma resta sintetico: max 200 parole. \
Non produrre ancora la decisione finale BUY/SELL/HOLD in modo formale: il tuo output qui e' solo \
l'analisi che ti servira' per decidere nel passo successivo.
"""

# --- Ensemble: personas specializzate + manager arbitro ------------------- #
# Stessa identita' di base (SYSTEM_PROMPT) con una specializzazione aggiunta:
# stesso modello, prospettive diverse per costruire un vero disaccordo/accordo
# misurabile, invece di un numero di confidenza inventato dal modello stesso.

TECHNICAL_PERSONA_SYSTEM_PROMPT = SYSTEM_PROMPT + """
SPECIALIZZAZIONE: Analista Tecnico del desk.
In questa fase agisci come lo specialista tecnico: basa la tua decisione principalmente su \
prezzo, struttura di mercato e indicatori (RSI, EMA, MACD, ATR, Bollinger Bands) e sul loro \
allineamento col trend del timeframe superiore. Tratta le notizie fornite come contesto \
secondario: non capovolgere una lettura tecnica chiara solo per una notizia, a meno che non sia \
direttamente e fortemente rilevante per l'asset.
"""

MACRO_PERSONA_SYSTEM_PROMPT = SYSTEM_PROMPT + """
SPECIALIZZAZIONE: Analista Macro/Sentiment del desk.
In questa fase agisci come lo specialista macro/news: stabilisci la direzione principalmente in \
base alle notizie fornite e al trend di fondo (timeframe superiore). Usa gli indicatori tecnici \
in un ruolo secondario, solo per affinare i livelli di entry, take profit e stop loss — non per \
ribaltare la direzione suggerita dal contesto macro/news.
"""

MANAGER_SYSTEM_PROMPT = SYSTEM_PROMPT + """
SPECIALIZZAZIONE: Risk Manager del desk (arbitro finale).
Due analisti indipendenti (uno tecnico, uno macro/news) hanno gia' prodotto un verdetto separato \
sullo stesso asset, riportati piu' sotto nel prompt. Il tuo compito e' emettere il verdetto \
finale, seguendo queste regole di arbitraggio:
- Se i due analisti concordano sulla stessa azione (BUY o BUY, oppure SELL o SELL), quella e' di \
norma la scelta piu' solida: adottala, eventualmente affinando TP/SL con la tua supervisione.
- Se sono in disaccordo netto (uno BUY, l'altro SELL), il default e' HOLD, a meno che uno dei due \
non presenti un'evidenza tecnica o di trend nettamente piu' solida e verificabile nei dati forniti \
sopra (non fidarti ciecamente delle loro motivazioni: ricontrolla tu stesso i numeri).
- Se uno dei due propone HOLD e l'altro un'azione, applica una cautela extra: preferisci HOLD \
salvo un'evidenza molto forte a favore dell'azione proposta.
Non ignorare mai il vincolo di rapporto rischio/rendimento minimo 1:1.5 gia' definito sopra, \
indipendentemente da cosa propongano gli analisti.
"""


def _format_news(news_items: List[NewsItem]) -> str:
    if not news_items:
        return "Nessuna notizia rilevante disponibile."
    lines = []
    for i, item in enumerate(news_items, start=1):
        lines.append(
            f"{i}. [{item['source']} | {item['published_at']}] {item['headline']}\n"
            f"   {item['summary']}"
        )
    return "\n".join(lines)


def _format_htf_trend(htf_trend: Optional[dict]) -> str:
    if not htf_trend:
        return "Non disponibile."
    ema_key = next((k for k in htf_trend if k.startswith("ema_")), None)
    ema_val = htf_trend.get(ema_key) if ema_key else None
    return (
        f"Timeframe: {htf_trend.get('timeframe')} | Trend: {htf_trend.get('trend')} | "
        f"Ultimo prezzo: {htf_trend.get('last_close')} | {ema_key or 'EMA'}: {ema_val}"
    )


def build_user_prompt(
    symbol: str,
    timeframe: str,
    market_payload: dict,
    news_items: List[NewsItem],
    account_balance: float,
    risk_per_trade_pct: float,
    htf_trend: Optional[dict] = None,
    preliminary_analysis: Optional[str] = None,
) -> str:
    """
    Costruisce il prompt utente da inviare a Qwen combinando dati di mercato,
    indicatori, trend multi-timeframe e notizie in un unico blocco testuale.

    Se `preliminary_analysis` e' fornita (output della fase di ragionamento
    libero, vedi REASONING_SYSTEM_PROMPT), viene inclusa cosi' che il modello
    possa basare il verdetto finale sulla propria analisi gia' elaborata.
    """
    ohlcv_json = json.dumps(market_payload["candles"], separators=(",", ":"))
    indicators = market_payload["indicators"]

    prompt = f"""### CONTESTO OPERATIVO
Asset: {symbol}
Timeframe: {timeframe}
Capitale conto: {account_balance:.2f} EUR
Rischio massimo per trade: {risk_per_trade_pct:.2f}%

### DATI OHLCV (ultime candele, formato [timestamp, open, high, low, close, volume])
{ohlcv_json}

### INDICATORI TECNICI CORRENTI ({timeframe})
RSI(14): {indicators.get('rsi_14')}
EMA(20): {indicators.get('ema_20')}
MACD: {indicators.get('macd')} | Signal: {indicators.get('macd_signal')} | Hist: {indicators.get('macd_hist')}
ATR(14): {indicators.get('atr_14')}
Bollinger Bands: lower={indicators.get('bb_lower')} mid={indicators.get('bb_mid')} upper={indicators.get('bb_upper')}
Ultimo prezzo di chiusura: {indicators.get('last_close')}

### TREND TIMEFRAME SUPERIORE (conferma/contraddice il segnale M15)
{_format_htf_trend(htf_trend)}

### NOTIZIE RECENTI
{_format_news(news_items)}
"""

    if preliminary_analysis:
        prompt += f"""
### LA TUA ANALISI PRELIMINARE (gia' elaborata nel passo precedente)
{preliminary_analysis}
"""

    prompt += """
### RICHIESTA
In base a tutto il contesto sopra riportato (dati di mercato, indicatori, trend multi-timeframe, \
notizie""" + (""" e la tua analisi preliminare""" if preliminary_analysis else "") + """), \
genera il segnale di trading nel formato JSON obbligatorio definito nel system prompt.
"""
    return prompt


def build_manager_prompt(
    symbol: str,
    timeframe: str,
    market_payload: dict,
    news_items: List[NewsItem],
    account_balance: float,
    risk_per_trade_pct: float,
    htf_trend: Optional[dict],
    persona_signals: dict,
) -> str:
    """
    Prompt per il manager: stesso contesto di mercato di `build_user_prompt`,
    con in coda i verdetti indipendenti delle personas (dict {nome: TradeSignal})
    e una richiesta finale di arbitraggio (vedi MANAGER_SYSTEM_PROMPT).
    """
    base = build_user_prompt(
        symbol=symbol, timeframe=timeframe, market_payload=market_payload,
        news_items=news_items, account_balance=account_balance,
        risk_per_trade_pct=risk_per_trade_pct, htf_trend=htf_trend,
    )

    personas_block = "\n".join(
        f"- {name} → action: {sig['action']}, TP: {sig['take_profit_price']}, "
        f"SL: {sig['stop_loss_price']}, confidenza dichiarata: {sig['confidence_percentage']}%\n"
        f"  motivazione: {sig['reasoning']}"
        for name, sig in persona_signals.items()
    )

    missing_note = ""
    if len(persona_signals) < 2:
        missing_note = (
            f"\n(ATTENZIONE: solo {len(persona_signals)} analista su 2 e' disponibile. Senza un "
            "secondo parere indipendente preferisci HOLD salvo evidenza molto forte nei dati.)"
        )

    return (
        base
        + "\n\n### VERDETTI INDIPENDENTI DEGLI ANALISTI DEL DESK\n"
        + personas_block
        + missing_note
        + "\n\n### RICHIESTA FINALE (sostituisce la richiesta precedente)\n"
        "Tenendo conto di entrambi i verdetti sopra e delle regole di arbitraggio definite nel "
        "system prompt, emetti ORA il verdetto finale nel formato JSON obbligatorio."
    )
