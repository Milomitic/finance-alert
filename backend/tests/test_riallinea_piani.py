"""FA-168: i piani a finestra chiusa si riallineano alle barre corrette dopo."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import update

from app.models import OhlcvDaily, PlanOutcome, PlanOutcomeOmbra
from app.services import plan_outcome_service as pos
from app.services import uscite_ombra_service as uo
from app.services.signal_drift_service import _horizon_days
from app.signals.trade_plan import sedute_della_gara
from tests.test_maturazione_piani import _alert, _barre, _titolo


def _scaduto(db):
    """Un piano che non tocca ne' stop (96) ne' target (106) e scade."""
    s = _titolo(db)
    a = _alert(db, s)
    h = sedute_della_gara("sr_flip", _horizon_days("sr_flip"))
    giorni = [date(2026, 3, 2) + timedelta(days=i) for i in range(h + 3)]
    _barre(db, s, [(g.isoformat(), 101.0, 99.0, 100.0 + (i % 3) * 0.5) for i, g in enumerate(giorni)])
    pos.mature_plan_outcomes(db, commit=False)
    db.commit()
    return s, a, h, giorni


def test_una_chiusura_corretta_dopo_riallinea_il_piano(db):
    s, a, h, giorni = _scaduto(db)
    riga = db.query(PlanOutcome).one()
    assert riga.esito == "scaduto" and riga.legs_window_complete
    prima = riga.r_multiple
    uo.matura(db)
    assert db.query(PlanOutcomeOmbra).count() > 0
    # Nessun cambiamento nei dati: niente da riallineare.
    assert pos.riallinea_piani(db) == (1, 0)

    # La barra d'uscita (l'ultima della finestra) viene corretta.
    uscita = giorni[h]
    db.execute(update(OhlcvDaily).where(OhlcvDaily.stock_id == s.id, OhlcvDaily.date == uscita)
               .values(close=OhlcvDaily.close + 2))
    db.commit()
    assert pos.riallinea_piani(db) == (1, 1)
    db.refresh(riga)
    assert riga.r_multiple > prima and riga.esito == "scaduto"
    # Le varianti in prova si rimisurano sulla geometria nuova.
    assert db.query(PlanOutcomeOmbra).count() == 0
    assert pos.riallinea_piani(db) == (1, 0)


def test_una_riga_che_oggi_non_si_calcola_resta_com_era(db):
    s, a, h, giorni = _scaduto(db)
    prima = db.query(PlanOutcome).one().r_multiple
    # La serie viene accorciata da una riparazione: la gara torna aperta.
    db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == s.id, OhlcvDaily.date > giorni[3]).delete()
    db.commit()
    assert pos.riallinea_piani(db) == (1, 0)
    assert db.query(PlanOutcome).one().r_multiple == prima


def test_senza_piani_chiusi_niente(db):
    assert pos.riallinea_piani(db) == (0, 0)


def test_il_diverso_tollera_il_rumore_dei_float():
    assert not pos._diverso(1.0, 1.0 + 1e-12)
    assert pos._diverso(1.0, 1.1)
    assert pos._diverso(None, 1.0) and not pos._diverso(None, None)
    assert pos._diverso("tp1", "stop")
