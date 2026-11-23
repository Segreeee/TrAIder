"""P6.02: rendering HTML statico della dashboard (D-009). Offline, una colonna per il telefono, ogni numero del
view-model visibile. Lo snapshot si rigenera solo con TRAIDER_UPDATE_SNAPSHOT=1, poi si rivede il diff."""
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from adapters.sqlite_store import SqliteStore
from report.dashboard import render
from report.viewmodel import load_archive, viewmodel
from tests.report.test_viewmodel import db  # noqa: F401 (fixture)

SNAPSHOT = Path(__file__).parent / "snapshots" / "dashboard.html"
NOW = datetime(2026, 12, 1, 13, 5, tzinfo=timezone.utc)


def _html(path):
    return render(viewmodel(load_archive(path), production_variant="v7-completo"), generated_at=NOW)


def test_snapshot_matches(db):  # noqa: F811
    html = _html(db)
    if os.environ.get("TRAIDER_UPDATE_SNAPSHOT") == "1":
        SNAPSHOT.write_text(html, encoding="utf-8")
    assert html == SNAPSHOT.read_text(encoding="utf-8")


def test_every_viewmodel_number_rendered(db):  # noqa: F811
    vm = viewmodel(load_archive(db), production_variant="v7-completo")
    html = _html(db)
    for s in vm["signals"]:
        assert f"{s['p']:.2f}" in html and f"{s['p_star']:.2f}" in html and s["symbol"] in html
    assert f"{vm['curve'][-1]['net']:+.2f}" in html and f"{vm['curve'][-1]['gross']:+.2f}" in html
    for k in ("cycles_done", "cycles_error", "resolved", "pending"):
        assert f">{vm['coverage'][k]}<" in html
    assert "EUR +1" in html and "USD −1" in html
    assert f"{vm['progress']['n']} su {vm['progress']['n_target']}" in html
    assert f"{vm['progress']['days']} su {vm['progress']['days_target']}" in html
    for v in vm["variants"]:
        if v["available"]:
            assert v["name"] in html
    assert "non concludente" in html.lower()


def test_no_external_urls(db):  # noqa: F811
    html = _html(db)
    assert not re.search(r"(https?:)?//[\w.-]+\.\w", html)  # niente CDN, font o script esterni: funziona offline
    assert "<script src" not in html and "<link" not in html


def test_viewport_meta_present(db):  # noqa: F811
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in _html(db)


def test_text_from_archive_is_escaped(tmp_path):
    from tests.report.test_viewmodel import _cycle
    path = tmp_path / "x.db"
    store = SqliteStore(str(path))
    _cycle(store, "<img src=x onerror=alert(1)>", NOW, "HOLD")  # l'archivio è a sola aggiunta: si scrive così
    store.close()
    html = _html(path)
    assert "<img src=x" not in html and "&lt;img" in html


def test_stale_daemon_is_flagged(db):  # noqa: F811
    vm = viewmodel(load_archive(db), production_variant="v7-completo")
    fresh = render(vm, generated_at=datetime.fromisoformat(vm["last_cycle"]))
    stale = render(vm, generated_at=datetime(2026, 12, 2, 13, 0, tzinfo=timezone.utc))
    assert "nessun ciclo da" not in fresh and "nessun ciclo da" in stale
