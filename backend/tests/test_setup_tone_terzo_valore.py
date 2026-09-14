"""I toni di un setup sono TRE, e le tre voci devono sommare al totale.

FA-061. Finche' i toni erano due, `active_bull + active_bear == active` tornava
per caso e nessuno lo asseriva. Da quando `squeeze_expansion` dichiara di non
conoscere il verso, mostrare solo rialzisti e ribassisti lascerebbe un resto
senza nome sotto un totale che non torna — e chi legge non avrebbe modo di
sapere dov'e' finito. E' la famiglia di difetti che l'audit UI ha gia' censito:
«due riquadri con etichette diverse non devono stampare lo stesso numero», qui
nella variante «le parti devono fare il tutto».
"""
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Stock
from app.models.stock_setup import STATUS_ACTIVE, StockSetup
from app.services.setup_service import conversion_stats
from app.signals.setups.base import TONE_BEAR, TONE_BULL, TONE_UNDETERMINED

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_SEQ = {"n": 0}


def _attivo(db: Session, tone: str, detector: str = "trend_pullback"):
    _SEQ["n"] += 1
    k = _SEQ["n"]
    stock = Stock(ticker=f"A{k}", exchange="NASDAQ", name=f"A{k}")
    db.add(stock)
    db.flush()
    db.add(StockSetup(
        stock_id=stock.id, detector=detector, tone=tone,
        proximity=0.6, convenience=55.0, missing="—", factors_json="{}",
        status=STATUS_ACTIVE, shortlisted=True,
        first_seen_at=NOW - timedelta(days=3), last_seen_at=NOW,
    ))
    db.commit()


def test_le_tre_voci_sommano_agli_attivi(db):
    for _ in range(3):
        _attivo(db, TONE_BULL)
    _attivo(db, TONE_BEAR)
    for _ in range(2):
        _attivo(db, TONE_UNDETERMINED, detector="squeeze_expansion")

    s = conversion_stats(db)
    assert (s["active_bull"], s["active_bear"], s["active_undetermined"]) == (3, 1, 2)
    assert s["active_bull"] + s["active_bear"] + s["active_undetermined"] == s["active"]


def test_un_setup_senza_direzione_non_finisce_fra_i_ribassisti(db):
    """⚠️ Il modo sbagliato di aggiungere un terzo valore.

    Il frontend scriveva `const bull = tone === "bull"`, e il conteggio
    equivalente sul backend sarebbe `active_bear = active - active_bull`. Con
    quella forma una compressione diventa ribassista: la direzione SBAGLIATA,
    con la stessa sicurezza di prima.
    """
    _attivo(db, TONE_UNDETERMINED, detector="squeeze_expansion")
    s = conversion_stats(db)
    assert s["active_bear"] == 0
    assert s["active_undetermined"] == 1


def test_le_costanti_non_obbligano_a_importare_il_modello():
    """⚠️ La proprieta' da cui dipende tutto il resto, e che non si vede.

    I toni vivono accanto a `SetupMatch.tone` che dichiarano, non sul modello:
    `app/models/stock_setup.py` porta SQLAlchemy, e un detector di puro calcolo
    che dovesse importarlo per leggere una stringa si tirerebbe dietro meta'
    stack. Se qualcuno li sposta, la costante torna scomoda da importare e la
    prossima persona la riscrive a mano — che e' esattamente come
    `app/indicators/periods.py` si ritrovo' quattordici copie.

    ⚠️ Si misura in un PROCESSO NUOVO, e la prima versione di questo test non
    lo faceva: dentro pytest `sqlalchemy` e' gia' in `sys.modules` perche' il
    conftest l'ha caricato, quindi svuotare i soli moduli `app.*` lascia
    l'asserzione falsa di qualunque cosa. Un controllo sull'import sporcato da
    cio' che gia' gira non misura l'import.
    """
    fuori = subprocess.run(
        [sys.executable, "-c",
         "import sys;"
         "import app.signals.detectors.squeeze_expansion;"
         "print('sqlalchemy' in sys.modules)"],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
        check=False,
    )
    assert fuori.returncode == 0, fuori.stderr
    assert fuori.stdout.strip() == "False", (
        "il detector della compressione si tira dietro SQLAlchemy: le costanti "
        "dei toni sono state spostate su un modulo che porta i modelli"
    )
