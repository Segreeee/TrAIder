"""
Configurazione centralizzata dell'MVP.
Tutti i parametri sensibili/ambientali vengono letti da variabili d'ambiente
(caricate da un file .env in fase di sviluppo) cosi' da non hardcodare
credenziali nel codice sorgente.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # --- LLM (Qwen via endpoint OpenAI-compatible) ---
    qwen_api_key: str = os.getenv("QWEN_API_KEY", "")
    qwen_base_url: str = os.getenv(
        "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen-plus")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # --- Analisti locali (Ollama, endpoint OpenAI-compatible) ---
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ollama_model_technical: str = os.getenv("OLLAMA_MODEL_TECHNICAL", "gemma3:12b")
    ollama_model_macro: str = os.getenv("OLLAMA_MODEL_MACRO", "gemma3:12b")
    ollama_model_judge: str = os.getenv("OLLAMA_MODEL_JUDGE", "gemma3:12b")
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))

    # --- MetaTrader5 ---
    mt5_login: str = os.getenv("MT5_LOGIN", "")
    mt5_password: str = os.getenv("MT5_PASSWORD", "")
    mt5_server: str = os.getenv("MT5_SERVER", "")
    mt5_path: str = os.getenv("MT5_PATH", "")

    # --- Trading ---
    symbol: str = os.getenv("SYMBOL", "EURUSD")
    symbols: tuple = tuple(
        s.strip().upper()
        for s in os.getenv("SYMBOLS", "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF").split(",")
        if s.strip()
    )
    timeframe: str = os.getenv("TIMEFRAME", "M15")
    candles_count: int = int(os.getenv("CANDLES_COUNT", "50"))
    account_balance: float = float(os.getenv("ACCOUNT_BALANCE", "10000"))
    risk_per_trade_pct: float = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
    loop_interval_seconds: int = int(os.getenv("LOOP_INTERVAL_SECONDS", "900"))
    dry_run: bool = _get_bool("DRY_RUN", True)
    # Secondo consenso per gli ordini reali: serve anche DRY_RUN=false.
    allow_live_trading: bool = _get_bool("ALLOW_LIVE_TRADING", False)

    # --- Notizie ---
    # "none" (default): nessuna notizia, analista macro escluso.
    # "mock": notizie statiche inventate, consentite solo con DRY_RUN=true.
    news_provider: str = os.getenv("NEWS_PROVIDER", "none")

    # --- Costi e limiti di portafoglio ---
    cost_pips: float = float(os.getenv("COST_PIPS", "1.0"))  # spread+commissioni+slippage, andata e ritorno
    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
    max_currency_exposure: int = int(os.getenv("MAX_CURRENCY_EXPOSURE", "1"))  # posizioni nette per valuta
    daily_loss_limit_pct: float = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "3.0"))
    magic_number: int = int(os.getenv("MAGIC_NUMBER", "990011"))


settings = Settings()
