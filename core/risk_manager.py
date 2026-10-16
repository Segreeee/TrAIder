"""
Risk Management.

Calcola il lot size massimo consigliato dato:
- il capitale disponibile (account_balance),
- la percentuale di rischio massima per trade (risk_per_trade_pct),
- la distanza in pip tra entry e stop loss.

Formula standard (per coppie XXX/USD dove 1 lotto standard = 100.000 unita'):
    pip_value_per_lot = 10 USD/pip  (valido per EURUSD, 1 lotto standard)
    risk_amount = account_balance * (risk_pct / 100)
    lot_size = risk_amount / (sl_distance_pips * pip_value_per_lot)

Il risultato viene arrotondato al passo minimo di 0.01 lotti (micro-lotto)
e limitato a un massimo di sicurezza configurabile.
"""
import logging
import math

logger = logging.getLogger(__name__)

PIP_VALUE_PER_STANDARD_LOT_USD = 10.0  # valido per EURUSD con conto in USD/EUR
MIN_LOT = 0.01
LOT_STEP = 0.01
MAX_LOT_SAFETY_CAP = 5.0


MIN_RISK_REWARD_RATIO = 1.5


def compute_risk_reward_ratio(entry_price: float, take_profit_price: float, stop_loss_price: float) -> float:
    """Rapporto reward/risk reale (calcolato da noi, non dichiarato dall'LLM) tra TP e SL rispetto all'entry."""
    reward = abs(take_profit_price - entry_price)
    risk = abs(entry_price - stop_loss_price)
    if risk <= 0:
        return 0.0
    return reward / risk


def meets_min_risk_reward(
    entry_price: float, take_profit_price: float, stop_loss_price: float, min_ratio: float = MIN_RISK_REWARD_RATIO,
) -> bool:
    """
    Verifica indipendente che TP/SL rispettino davvero il rapporto minimo
    richiesto nel system prompt (1:1.5). L'LLM a volte dichiara nel campo
    'reasoning' un R:R corretto usando pero' cifre sbagliate: questo controllo
    non si fida del testo generato, ricalcola i prezzi effettivi.
    """
    return compute_risk_reward_ratio(entry_price, take_profit_price, stop_loss_price) >= min_ratio


def pip_size_for_symbol(symbol: str) -> float:
    """
    Restituisce la dimensione di un pip per il simbolo dato: 0.01 per le coppie
    con JPY (es. USDJPY), 0.0001 per la generalita' delle altre coppie forex.
    Nota MVP: PIP_VALUE_PER_STANDARD_LOT_USD resta un'approssimazione fissa a
    10 USD/pip valida principalmente per le coppie con USD come valuta quotata
    (es. EURUSD, GBPUSD); per le altre (USDJPY, USDCAD, USDCHF) il valore
    reale del pip varia leggermente col tasso di cambio corrente.
    """
    return 0.01 if "JPY" in symbol.upper() else 0.0001


class RiskManager:
    def __init__(self, account_balance: float, risk_per_trade_pct: float):
        if account_balance <= 0:
            raise ValueError("account_balance deve essere positivo")
        if not (0 < risk_per_trade_pct <= 100):
            raise ValueError("risk_per_trade_pct deve essere in (0, 100]")

        self.account_balance = account_balance
        self.risk_per_trade_pct = risk_per_trade_pct

    def max_risk_amount(self) -> float:
        """Importo massimo (in valuta del conto) rischiabile su un singolo trade."""
        return self.account_balance * (self.risk_per_trade_pct / 100.0)

    def calculate_lot_size(self, entry_price: float, stop_loss_price: float, pip_size: float = 0.0001) -> float:
        """
        Calcola il lot size massimo consigliato dato un entry e uno stop loss.
        `pip_size` e' 0.0001 per la maggior parte delle coppie forex (0.01 per gli JPY-cross).
        """
        sl_distance_price = abs(entry_price - stop_loss_price)
        if sl_distance_price <= 0:
            logger.warning("Distanza SL nulla: impossibile calcolare il lot size, uso MIN_LOT.")
            return MIN_LOT

        sl_distance_pips = sl_distance_price / pip_size
        risk_amount = self.max_risk_amount()

        raw_lot = risk_amount / (sl_distance_pips * PIP_VALUE_PER_STANDARD_LOT_USD)

        # Arrotonda per difetto al passo minimo (non superare mai il rischio consentito)
        stepped_lot = math.floor(raw_lot / LOT_STEP) * LOT_STEP
        lot = max(MIN_LOT, min(stepped_lot, MAX_LOT_SAFETY_CAP))

        logger.info(
            "RiskManager: risk_amount=%.2f, sl_pips=%.1f, raw_lot=%.4f -> lot_size=%.2f",
            risk_amount, sl_distance_pips, raw_lot, lot,
        )
        return round(lot, 2)

    def cap_llm_lot_size(self, llm_lot_size: float, entry_price: float, stop_loss_price: float, pip_size: float = 0.0001) -> float:
        """
        Non ci si fida ciecamente del lot_size proposto dall'LLM: viene sempre
        confrontato con il massimo calcolabile dalla regola dell'1% e limitato
        al minore tra i due.
        """
        max_allowed = self.calculate_lot_size(entry_price, stop_loss_price, pip_size)
        if llm_lot_size is None or llm_lot_size <= 0:
            return max_allowed
        capped = min(llm_lot_size, max_allowed)
        return round(capped, 2)
