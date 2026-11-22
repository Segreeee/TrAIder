"""Diagnosi in SOLA LETTURA dello scarto tra ora del server MT5 e UTC (T-007, passo P3.05).

Uso (terminale MT5 installato, mercato aperto, giorno feriale), dalla cartella del progetto:
    python tools/diagnose_mt5_tz.py [SIMBOLO]

Le credenziali (MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH) arrivano dal .env tramite app.config;
la password non viene mai stampata. Chiama solo initialize, symbol_select, copy_rates_from_pos e
shutdown: nessuna funzione di trading.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.compose import mt5_init_kwargs  # noqa: E402
from app.config import Settings  # noqa: E402
from domain.clock import server_offset_hours  # noqa: E402

TF_MINUTES = 15


init_kwargs = mt5_init_kwargs  # stessa regola del demone (app.compose)


def main(argv: list[str], mt5, cfg: Settings) -> int:
    symbol = argv[0] if argv else "EURUSD"
    if not mt5.initialize(**init_kwargs(cfg)):
        print(f"initialize fallita: {mt5.last_error()}")
        print("Controlla: MT5 installato e aperto; nel .env MT5_LOGIN (numero del conto demo), "
              "MT5_PASSWORD e MT5_SERVER esattamente come in MT5 (File > Accedi al conto di trading).")
        return 1
    try:
        if not mt5.symbol_select(symbol, True):
            print(f"Simbolo non disponibile: {symbol}")
            return 1
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 1)  # barra in formazione
        now = datetime.now(timezone.utc)
        if rates is None or len(rates) == 0:
            print(f"Nessuna barra ricevuta: {mt5.last_error()}")
            return 1
        bar_open = int(rates[0]["time"])
        offset = server_offset_hours(bar_open, now, TF_MINUTES)
        print(f"UTC adesso:               {now.isoformat(timespec='seconds')}")
        print(f"Apertura barra (server):  {datetime.fromtimestamp(bar_open, tz=timezone.utc).replace(tzinfo=None)}")
        if offset is None:
            print("Scarto non determinabile: barra vecchia (mercato chiuso?). Riprova a mercato aperto.")
            return 2
        print(f"Scarto server - UTC:      {offset:+d} ore")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    import MetaTrader5  # solo qui: i test usano un MT5 finto
    raise SystemExit(main(sys.argv[1:], MetaTrader5, Settings()))
