"""Scheduler allineato alla chiusura della candela (D-010), solo libreria standard.

Il ciclo parte DELAY secondi dopo ogni chiusura M15. Un ciclo che dura più di OVERRUN_S fa saltare la
candela successiva (registrata nel log): meglio una candela persa che una elaborata in ritardo con dati
già vecchi. Le candele perse non si recuperano. Al riavvio si elabora l'ultima candela chiusa solo se
ha meno di RECOVERY_S secondi. Orologio e sleep sono iniettati: nei test non si aspetta mai davvero.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

log = logging.getLogger(__name__)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
OVERRUN_S, RECOVERY_S = 12 * 60, 5 * 60


def last_closed_candle(now: datetime, tf_min: int) -> datetime:
    tf = timedelta(minutes=tf_min)
    return EPOCH + ((now - EPOCH) // tf) * tf


def next_run(now: datetime, tf_min: int, delay_s: int) -> datetime:
    """Primo istante dopo `now` che cade `delay_s` secondi dopo una chiusura di candela."""
    t = last_closed_candle(now, tf_min) + timedelta(seconds=delay_s)
    return t if t > now else t + timedelta(minutes=tf_min)


def run_loop(cycle: Callable[[datetime], None], clock: Callable[[], datetime], sleep: Callable[[float], None],
             tf_min: int = 15, delay_s: int = 10, max_cycles: Optional[int] = None, recover: bool = False,
             overrun_s: int = OVERRUN_S, recovery_s: int = RECOVERY_S) -> list[datetime]:
    """Esegue `cycle(chiusura_candela)` una volta per candela. Restituisce le candele saltate."""
    tf, skipped, done = timedelta(minutes=tf_min), [], 0
    not_before: Optional[datetime] = None

    def run(candle: datetime) -> None:
        nonlocal done, not_before
        start = clock()
        try:
            cycle(candle)
        except Exception:  # un ciclo fallito non ferma il demone; run_once archivia già i propri errori
            log.exception("ciclo della candela %s fallito", candle.isoformat())
        done += 1
        elapsed = (clock() - start).total_seconds()
        not_before = None
        if elapsed > overrun_s:
            lost = candle + tf
            skipped.append(lost)
            log.warning("candela %s saltata: il ciclo precedente è durato %.0f s (limite %d s)",
                        lost.isoformat(), elapsed, overrun_s)
            not_before = lost + timedelta(seconds=delay_s)

    if recover:
        last = last_closed_candle(clock(), tf_min)
        if (clock() - last).total_seconds() <= recovery_s:
            run(last)
        else:
            log.info("riavvio: candela %s troppo vecchia, si aspetta la prossima", last.isoformat())

    while max_cycles is None or done < max_cycles:
        now = clock()
        t = next_run(max(now, not_before) if not_before else now, tf_min, delay_s)
        sleep((t - now).total_seconds())
        run(t - timedelta(seconds=delay_s))
    return skipped
