"""
Entry point CLI per il backtester.

Esempi:
    python backtest.py --symbol EURUSD --days 3 --stride 8
    python backtest.py --symbol USDJPY --days 7 --stride 16 --two-phase

Salva il log dei trade in logs/backtest_<symbol>_<timestamp>.csv e stampa un
riepilogo aggregato (win rate, R totale, espettanza per trade) a console.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import settings
from core.backtester import run_backtest, summarize, trades_to_dataframe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest walk-forward della pipeline TrAIder su dati storici MT5.")
    parser.add_argument("--symbol", default=settings.symbol, help=f"Simbolo da testare (default: {settings.symbol})")
    parser.add_argument("--timeframe", default=settings.timeframe, help=f"Timeframe (default: {settings.timeframe})")
    parser.add_argument("--days", type=int, default=3, help="Quanti giorni indietro partire (default: 3)")
    parser.add_argument("--stride", type=int, default=8, help="Candele tra un punto campionato e il successivo (default: 8)")
    parser.add_argument("--two-phase", action="store_true", help="Usa la pipeline a due fasi (analisi + verdetto), piu' lenta/costosa")
    parser.add_argument("--max-signals", type=int, default=None, help="Tetto di sicurezza sul numero di punti valutati")
    parser.add_argument("--balance", type=float, default=settings.account_balance, help="Capitale simulato")
    parser.add_argument("--risk-pct", type=float, default=settings.risk_per_trade_pct, help="Rischio massimo per trade (%%)")
    parser.add_argument("--cost-pips", type=float, default=settings.cost_pips,
                        help=f"Costo per operazione in pip, andata e ritorno (default: {settings.cost_pips})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)

    print(f"Backtest {args.symbol} {args.timeframe} | {start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} UTC")
    print(f"stride={args.stride} two_phase={args.two_phase} max_signals={args.max_signals}")
    print("In corso (ogni punto costa una o due chiamate LLM, puo' richiedere qualche minuto)...\n")

    def on_progress(i: int, total: int) -> None:
        sys.stdout.write(f"\r  punto {i + 1}/{total}")
        sys.stdout.flush()

    try:
        trades = run_backtest(
            symbol=args.symbol, timeframe=args.timeframe, start=start, end=end,
            account_balance=args.balance, risk_per_trade_pct=args.risk_pct,
            stride=args.stride, two_phase=args.two_phase, max_signals=args.max_signals,
            progress_callback=on_progress, cost_pips=args.cost_pips,
        )
    except ValueError as exc:
        print(f"\nErrore: {exc}")
        sys.exit(1)

    print("\n")
    stats = summarize(trades)
    print("=== RIEPILOGO ===")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    if trades:
        Path("logs").mkdir(exist_ok=True)
        out_path = Path(f"logs/backtest_{args.symbol}_{datetime.now():%Y%m%d_%H%M%S}.csv")
        trades_to_dataframe(trades).to_csv(out_path, index=False)
        print(f"\nDettaglio trade salvato in: {out_path}")
    else:
        print("\nNessun segnale valutato (range troppo corto o errori LLM su tutti i punti).")


if __name__ == "__main__":
    main()
