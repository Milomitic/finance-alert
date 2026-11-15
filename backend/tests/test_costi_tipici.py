"""I costi tipici di eToro e l'attesa netta dei piani (FA-142)."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import (
    CostoTipico,
    EtoroCatalogo,
    EtoroPosizione,
    EtoroStrumento,
    PlanOutcome,
    Stock,
)
from app.services import costi_tipici_service as ct
from app.services import plan_performance_service as pp
from app.services.etoro_catalogo_service import Costi, Voce
from app.services.plan_outcome_service import PLAN_METHOD_VERSION

C = ct.Costo(commissione_pct=0.0015, spread_pct=0.0001, notte_long_pct=0.0003, notte_short_pct=0.0)


def test_il_costo_in_r_dipende_dalla_distanza_dello_stop():
    # Stop al 2%: due commissioni e lo spread valgono 0,31% / 2% = 0,155 R.
    vicino = ct.costo_in_r(costo=C, ingresso=100, r=2, lato="long", notti=0, con_leva=False)
    lontano = ct.costo_in_r(costo=C, ingresso=100, r=10, lato="long", notti=0, con_leva=False)
    assert vicino == pytest.approx(0.155)
    assert lontano == pytest.approx(0.031)


def test_le_notti_solo_con_la_leva_e_secondo_il_lato():
    """21 sedute sono 29 giorni di calendario: il venerdi' eToro addebita il
    fine settimana, cioe' tre notti, e contare i giorni da' la stessa somma."""
    senza = ct.costo_in_r(costo=C, ingresso=100, r=5, lato="long", notti=29, con_leva=False)
    lungo = ct.costo_in_r(costo=C, ingresso=100, r=5, lato="long", notti=29, con_leva=True)
    corto = ct.costo_in_r(costo=C, ingresso=100, r=5, lato="short", notti=29, con_leva=True)
    assert lungo == pytest.approx(senza + 29 * 0.0003 / 0.05)
    assert corto == pytest.approx(senza)
    ignota = ct.Costo(0.0015, 0.0001, None, None)
    assert ct.costo_in_r(costo=ignota, ingresso=100, r=5, lato="long", notti=3, con_leva=True) is None
    assert ct.costo_in_r(costo=C, ingresso=100, r=0, lato="long", notti=0, con_leva=False) is None


def test_la_leva_tipica_e_la_mediana_del_conto(db):
    assert ct.leva_tipica(db) == ct.LEVA_PREDEFINITA
    db.add(EtoroStrumento(instrument_id=1, simbolo="X", abbinamento="auto",
                          aggiornato_il=datetime(2026, 1, 1, tzinfo=UTC)))
    db.flush()
    for i, leva in enumerate([1, 2, 5, 5, 10]):
        db.add(EtoroPosizione(position_id=i, instrument_id=1, lato="long", leva=leva,
                              regolamento="cfd", aperta_il=datetime(2026, 1, 1, tzinfo=UTC),
                              prezzo_apertura=1, unita=1, importo_usd=1,
                              vista_il=datetime(2026, 1, 1, tzinfo=UTC)))
    db.commit()
    assert ct.leva_tipica(db) == 5      # la leva 1 non conta


def _titoli(db, n=3):
    out = []
    for k in range(n):
        s = Stock(ticker=f"C{k}", exchange="X", name=f"C{k}", currency="USD" if k < 2 else "EUR")
        db.add(s)
        db.flush()
        db.add(EtoroCatalogo(stock_id=s.id, instrument_id=100 + k, simbolo=f"C{k}",
                             verificato_il=datetime(2026, 11, 1, tzinfo=UTC)))
        out.append(s)
    db.commit()
    return out


def _finto(chiamate, notte_long=None):
    notte_long = notte_long or {}

    def preventivo(db, ticker, *, lato, leva, importo, stop):
        chiamate.append((ticker, lato, leva))
        nozionale = importo * leva
        notte = 0.0 if lato == "short" else notte_long.get(ticker, 0.000282) * nozionale
        voci = [Voce("transactionFee", 0.0015 * nozionale, "USD", 0.0015 * nozionale),
                Voce("marketSpread", 0.0001 * nozionale, "USD", 0.0001 * nozionale),
                Voce("overnightFee", notte, "USD", notte)]
        return Costi(simbolo=ticker, voci=voci)
    return preventivo


def test_la_notte_long_e_del_titolo_e_la_short_della_valuta(db):
    """Il 2026-11-15 un rappresentante per valuta («A», notte 0,0502%) aveva
    dato la sua notte a ogni titolo in dollari."""
    _titoli(db)
    chiamate = []
    out = ct.aggiorna(db, pausa=0, preventivo=_finto(chiamate, {"C0": 0.000502}))
    assert out == {"titoli": 3, "scritti": 3, "falliti": 0, "valute": 2}
    assert all(c[2] == 5 for c in chiamate)                 # alla leva tipica
    assert sum(1 for c in chiamate if c[1] == "long") == 3
    assert sum(1 for c in chiamate if c[1] == "short") == 3  # <= 5 per valuta
    righe = {r.stock_id: r for r in db.query(CostoTipico).all()}
    notti = sorted(round(r.notte_long_pct, 6) for r in righe.values())
    assert notti == [0.000282, 0.000282, 0.000502]           # l'anomalo resta suo
    r = next(iter(righe.values()))
    assert r.commissione_pct == pytest.approx(0.0015)
    assert r.spread_pct == pytest.approx(0.0001)
    assert r.notte_short_pct == 0.0 and r.leva == 5


def test_la_notte_short_si_misura_su_cinque_titoli_per_valuta(db):
    _titoli(db, n=8)
    chiamate = []
    ct.aggiorna(db, pausa=0, preventivo=_finto(chiamate))
    corti = [c for c in chiamate if c[1] == "short"]
    # Due titoli in USD (tutti e due), sei in EUR (solo cinque).
    assert len(corti) == 2 + 5


def test_troppi_fallimenti_di_fila_fermano_il_job(db, monkeypatch):
    _titoli(db, n=8)
    monkeypatch.setattr(ct, "FALLIMENTI_MAX", 3)

    def rotto(*a, **k):
        raise RuntimeError("429")

    out = ct.aggiorna(db, pausa=0, preventivo=rotto)
    assert (out["falliti"], out["scritti"]) == (3, 0)


def test_il_pannello_porta_l_attesa_netta(db):
    s, altro, *_ = _titoli(db)
    db.add(CostoTipico(stock_id=s.id, commissione_pct=0.0015, spread_pct=0.0001,
                       notte_long_pct=0.0003, notte_short_pct=0.0, leva=5, valuta="USD",
                       aggiornato_il=datetime(2026, 11, 13, tzinfo=UTC)))
    from app.models import Alert

    for sid in (s.id, altro.id):
        a = Alert(stock_id=sid, signal_name="sr_flip", trigger_price=1.0,
                  triggered_at=datetime(2026, 10, 1, tzinfo=UTC), snapshot="{}")
        db.add(a)
        db.flush()
        d = date(2026, 10, 1)
        db.add(PlanOutcome(
            alert_id=a.id, stock_id=sid, detector="sr_flip", signal_date=d, tone="bull",
            horizon_days=21, entry_date=d, entry=100.0, stop=95.0, tp1=110.0, tp2=None, r=5.0,
            esito="tp1", resolved_date=d + timedelta(days=10), bars_to_outcome=8,
            r_multiple=2.0, mae_r=0.1, mfe_r=2.0, tp2_reached=False,
            method_version=PLAN_METHOD_VERSION, legs_window_complete=True,
            matured_at=datetime.now(UTC)))
    db.commit()
    riga = pp.compute_plan_performance(db)["rows"][0]
    netta = riga["expectancy_r_netta"]
    assert netta["n"] == 1 and riga["n"] == 2       # solo il titolo con i costi
    assert netta["leva_1"] == pytest.approx(2.0 - 0.0031 / 0.05)
    assert netta["leva_tipica"] == pytest.approx(2.0 - (0.0031 + 10 * 0.0003) / 0.05)
    assert netta["leva_1"] <= 2.0 and netta["leva"] == 5


def test_senza_costi_il_netto_e_assente(db):
    assert pp._netta([], {}, None) is None


def test_il_job_salta_senza_chiavi_e_altrimenti_aggiorna(db, monkeypatch):
    import app.core.db as dbm
    from app.core.config import settings
    from app.scheduler.jobs import costi_tipici as job

    chiamate = []
    monkeypatch.setattr(ct, "aggiorna", lambda d: chiamate.append(1))
    monkeypatch.setattr(dbm, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(settings, "etoro_api_key", "")
    job.run_costi_tipici()
    assert chiamate == []
    monkeypatch.setattr(settings, "etoro_api_key", "k")
    monkeypatch.setattr(settings, "etoro_user_key", "u")
    job.run_costi_tipici()
    assert chiamate == [1]
