"""Configurazione da variabili d'ambiente e .env, validata all'avvio (D-011).

Nessuna istanza a livello di modulo: la composizione crea Settings() una volta e la passa come argomento.
Un .env con nomi sconosciuti (per esempio le vecchie QWEN_*) blocca l'avvio invece di essere ignorato.
"""
import hashlib
import json
from typing import Annotated, Literal, Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

SECRET_FIELDS = {"mt5_password", "finnhub_api_key", "remote_judge_api_key"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True,
                                      extra="forbid", frozen=True)

    # --- Sicurezza: doppio consenso per gli ordini reali ---
    dry_run: bool = True
    allow_live_trading: bool = False

    # --- Mercato ---
    symbols: Annotated[tuple[str, ...], NoDecode] = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF")
    timeframe: Literal["M15"] = "M15"   # domain/clock.py stima l'offset del server fino a 30 minuti
    htf_timeframe: Literal["H1"] = "H1"
    candles_count: int = Field(200, ge=50, le=2000)
    horizon_bars: int = Field(96, ge=1, le=1000)

    # --- Rischio e portafoglio ---
    account_balance: float = Field(10_000, gt=0)          # capitale del broker simulato
    risk_per_trade_pct: float = Field(1.0, gt=0, le=5)
    kelly_lambda: float = Field(0.25, gt=0, le=1)
    ev_min: float = 0.0
    beta_kappa: float = Field(20, gt=0)
    min_trades_for_model: int = Field(100, ge=30)
    max_open_positions: int = Field(3, ge=1, le=20)
    max_currency_exposure: int = Field(1, ge=1, le=10)
    daily_loss_limit_pct: float = Field(3.0, gt=0, le=20)

    # --- Costi: c = spread (da MT5) + commissione + slippage ---
    commission_eur_per_lot: Optional[float] = Field(None, ge=0)  # andata e ritorno; obbligatoria fuori da DRY_RUN
    slippage_pips: float = Field(0.2, ge=0, le=10)

    # --- LLM locali (Ollama, API OpenAI-compatibile) ---
    ollama_base_url: str = "http://localhost:11434/v1"
    model_technical: str = "gemma3:12b"
    model_macro: str = "gemma3:12b"
    llm_timeout_seconds: float = Field(120, gt=0)
    llm_max_retries: int = Field(2, ge=0, le=5)
    llm_seed: int = 7

    # --- Revisore offline (D-012): locale + remoto opzionale, fornitore scelto dall'utente (Q-001) ---
    judge_model: Optional[str] = None
    remote_judge_base_url: Optional[str] = None
    remote_judge_model: Optional[str] = None
    remote_judge_api_key: Optional[SecretStr] = None
    remote_judge_sample_pct: float = Field(20, ge=0, le=100)

    # --- Notizie ---
    news_provider: Literal["none", "mock", "finnhub"] = "none"
    finnhub_api_key: Optional[SecretStr] = None

    # --- MetaTrader5 ---
    mt5_login: str = ""
    mt5_password: SecretStr = SecretStr("")
    mt5_server: str = ""
    mt5_path: str = ""
    magic_number: int = 990011

    # --- Archivio ---
    db_path: str = "data/traider.db"

    @field_validator("symbols", mode="before")
    @classmethod
    def _split_symbols(cls, v):
        if isinstance(v, str):
            v = v.split(",")
        return tuple(s.strip().upper() for s in v if s.strip())

    @model_validator(mode="after")
    def _cross_checks(self):
        live = not self.dry_run
        if live and not self.allow_live_trading:
            raise ValueError("DRY_RUN disattivato senza il secondo consenso ALLOW_LIVE_TRADING=true")
        if live and self.news_provider == "mock":
            raise ValueError("NEWS_PROVIDER=mock è ammesso solo in DRY_RUN")
        if live and self.commission_eur_per_lot is None:
            raise ValueError("fuori da DRY_RUN serve COMMISSION_EUR_PER_LOT: un costo sottostimato sottostima il rischio")
        if self.news_provider == "finnhub" and not self.finnhub_api_key:
            raise ValueError("NEWS_PROVIDER=finnhub richiede FINNHUB_API_KEY")
        remote = (self.remote_judge_base_url, self.remote_judge_model, self.remote_judge_api_key)
        if any(remote) and not all(remote):
            raise ValueError("giudice remoto: servono REMOTE_JUDGE_BASE_URL, REMOTE_JUDGE_MODEL e REMOTE_JUDGE_API_KEY")
        return self

    def config_hash(self) -> str:
        """Impronta della configurazione senza segreti: va in ogni ciclo archiviato."""
        data = self.model_dump(mode="json", exclude=SECRET_FIELDS)
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
