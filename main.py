"""TrAIder: radice di composizione del demone (D-001, D-010).

    python main.py           ciclo continuo, allineato alla chiusura di ogni candela M15
    python main.py --once    elabora solo l'ultima candela chiusa ed esce

Configurazione solo da .env / variabili d'ambiente (app.config), validata all'avvio.
Default: DRY_RUN con broker simulato. Il broker MT5 si costruisce solo con il doppio consenso
(DRY_RUN=false E ALLOW_LIVE_TRADING=true), e il suo costruttore lo ricontrolla.
MetaTrader5 serve comunque per i dati di mercato: il terminale deve essere installato.
"""
import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic import ValidationError

from app.compose import build_ports, make_cycle, mt5_init_kwargs
from app.config import Settings
from app.scheduler import last_closed_candle, run_loop

log = logging.getLogger("traider")


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in (logging.StreamHandler(sys.stdout),
                    RotatingFileHandler("logs/traider.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)


def code_version() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "sconosciuta"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    setup_logging()
    try:
        cfg = Settings()
    except ValidationError as exc:  # solo nomi dei campi e tipo di errore: mai i valori (potrebbero essere segreti)
        for err in exc.errors():
            log.error("configurazione non valida: %s (%s)", ".".join(map(str, err["loc"])), err["type"])
        return 1

    import MetaTrader5 as mt5  # solo qui: i test non lo importano mai
    if not mt5.initialize(**mt5_init_kwargs(cfg)):
        log.error("MetaTrader5 non inizializzato: %s", mt5.last_error())
        return 1
    ports = None
    try:
        ports = build_ports(cfg, mt5)
        version = code_version()
        log.info("avvio TrAIder %s | DRY_RUN=%s | broker=%s | simboli=%s | variante di produzione=%s",
                 version, cfg.dry_run, type(ports.broker).__name__, ",".join(cfg.symbols), cfg.production_variant)
        cycle = make_cycle(cfg, ports, version)
        if args.once:
            cycle(last_closed_candle(utc_now(), 15))
        else:
            run_loop(cycle, utc_now, time.sleep, recover=True)
        return 0
    except KeyboardInterrupt:
        log.info("interruzione manuale (Ctrl+C)")
        return 0
    except Exception:  # Ollama giù, modello mancante, archivio illeggibile: nel log, non solo su stderr
        log.exception("TrAIder fermato da un errore")
        return 1
    finally:
        if ports is not None:
            ports.store.close()
        mt5.shutdown()
        log.info("TrAIder arrestato")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TrAIder: segnali forex con LLM come analisti")
    parser.add_argument("--once", action="store_true", help="elabora solo l'ultima candela chiusa ed esce")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
