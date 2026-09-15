"""Una scansione parziale non puo' dichiarare scaduto cio' che non ha guardato.

FA-062. `run_post_scan_bookkeeping` esisteva dal 2026-09-02 come proprietario
comune delle operazioni di fine scansione — nato perche' il percorso manuale e
quello del cron ne facevano due diverse — ma non prendeva PERIMETRO. `/scan`
accetta `stock_ids`: con un sottoinsieme il lavoro vero (fetch + segnali) resta
giusto, mentre la contabilita' finale parla di titoli che nessuno ha riosservato.

⚠️ Il difetto e' latente, non attivo: misurate in produzione il 2026-09-14, le
scansioni riuscite sono 436, di cui 37 parziali e TUTTE di maggio (quando
l'universo veniva potato); negli ultimi dieci giorni, 75 complete e 0 parziali.
Ma FA-061 ne ha alzato il prezzo — una chiusura sbagliata ora scrive
`closed_reason = 'stale'` in modo PERMANENTE e finisce nel denominatore del
tasso di conversione. Cioe' degrada un numero a schermo restando plausibile,
che e' la forma che questo progetto paga piu' spesso.
"""
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.models import Stock
from app.models.scan_run import KIND_ALERTS_SCAN, ScanRun
from app.models.stock_setup import (
    REASON_STALE,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    StockSetup,
)
from app.services import setup_service
from app.services.setup_service import _EXPIRE_AFTER_DAYS


def _scansioni_riuscite(db, n=5):
    """La guardia di `expire_stale_setups` pretende che la pipeline giri."""
    ora = datetime.now(UTC)
    for i in range(n):
        db.add(ScanRun(
            kind=KIND_ALERTS_SCAN, trigger="cron", status="success",
            started_at=ora - timedelta(days=1),
            completed_at=ora - timedelta(hours=i + 1),
            progress_done=0, progress_total=0,
        ))
    db.commit()


def _setup_decaduto(db):
    """Un setup non riosservato da ben oltre la soglia.

    Costruito RELATIVAMENTE all'adesso, non su una data scritta: la soglia e'
    in giorni e una data fissa smetterebbe di essere «decaduta» col passare
    del tempo — la stessa dipendenza dall'orologio che il seme e2e ha gia'
    pagato tre volte.
    """
    ora = datetime.now(UTC)
    stock = Stock(ticker="DECAY", exchange="NASDAQ", name="Decay", country="US")
    db.add(stock)
    db.flush()
    row = StockSetup(
        stock_id=stock.id, detector="oversold_reversal", tone="bull",
        proximity=0.8, convenience=70.0, missing="la barra deve girare",
        factors_json="{}", annotations_json="{}", status=STATUS_ACTIVE,
        first_seen_at=ora - timedelta(days=_EXPIRE_AFTER_DAYS + 6),
        last_seen_at=ora - timedelta(days=_EXPIRE_AFTER_DAYS + 5),
        shortlisted=True,
    )
    db.add(row)
    db.commit()
    return row


def test_una_scansione_dell_universo_ritira_cio_che_e_decaduto(db):
    """Il controllo POSITIVO, e va letto prima dell'altro.

    Senza, il test sul perimetro parziale sarebbe vero anche di un setup che
    non e' decaduto affatto: «resta attivo» non direbbe niente.
    """
    _scansioni_riuscite(db)
    row = _setup_decaduto(db)

    setup_service.run_post_scan_bookkeeping(db, universe=True)

    db.refresh(row)
    assert row.status == STATUS_EXPIRED
    assert row.closed_reason == REASON_STALE


def test_una_scansione_parziale_non_dichiara_scaduto_niente(db):
    """LO STESSO setup, lo stesso stato, solo il perimetro cambia."""
    _scansioni_riuscite(db)
    row = _setup_decaduto(db)

    setup_service.run_post_scan_bookkeeping(db, universe=False)

    db.refresh(row)
    assert row.status == STATUS_ACTIVE
    # ⚠️ E soprattutto: nessuna RAGIONE scritta. Da FA-061 `closed_reason` e'
    # permanente, quindi una chiusura sbagliata non e' un errore transitorio
    # ma una riga di storia falsa.
    assert row.closed_reason is None


def test_il_perimetro_e_obbligatorio(db):
    """Nessun valore di default, e questo test lo fissa.

    Un default a True darebbe il comportamento pericoloso a chi si dimentica
    di dichiarare, che e' esattamente l'errore da rendere impossibile. Il
    fallimento deve essere in chiamata, non in produzione.
    """
    with pytest.raises(TypeError):
        setup_service.run_post_scan_bookkeeping(db)  # type: ignore[call-arg]


def test_ogni_chiamante_dichiara_il_proprio_perimetro():
    """Censimento sulla SORGENTE, non sul comportamento.

    Un terzo chiamante che scrivesse `universe=True` per far compilare — o che
    ricevesse un default reintrodotto — non romperebbe nessun test di
    comportamento: passerebbe la contabilita' completa a una scansione
    parziale e il difetto tornerebbe con la suite verde. Stessa forma del
    censimento dei periodi degli indicatori.
    """
    radice = Path(__file__).resolve().parents[1] / "app"
    chiamate: list[tuple[str, str]] = []
    for f in radice.rglob("*.py"):
        for riga in f.read_text(encoding="utf-8").splitlines():
            if "run_post_scan_bookkeeping(" in riga and "def " not in riga:
                chiamate.append((f.name, riga.strip()))

    assert len(chiamate) == 3, f"chiamanti inattesi: {chiamate}"
    per_file = dict(chiamate)
    # Il cron guarda sempre tutto.
    assert re.search(r"universe=True", per_file["scan_alerts.py"])
    # ⚠️ Il seme del gate e2e (FA-074) e' il terzo, ed e' la forma che questo
    # censimento esiste per fermare — `universe=True` scritto a mano — quindi
    # va detto perche' qui e' vero e non comodo: `valuta_senza_rete` chiama
    # `run_tracked_scan`, cioe' `scan_universe` sull'INTERO catalogo seminato,
    # la stessa fase di valutazione del cron senza lo scaricamento. Se un giorno
    # valutasse un sottoinsieme, questa riga andrebbe cambiata insieme a quella.
    assert re.search(r"universe=True", per_file["seed_e2e.py"])
    # Il percorso manuale e' l'unico che puo' avere un sottoinsieme, e il suo
    # perimetro va DERIVATO da quello che ha davvero ricevuto.
    assert re.search(r"universe=stock_ids is None", per_file["alerts.py"])
