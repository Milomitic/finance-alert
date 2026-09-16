"""Il tasso di conversione ha un termine di paragone, e il paragone e' prudente.

«Il 48% dei setup converte» non dice niente da solo: dipende da quanto spesso lo
stesso segnale scatta comunque. Questi test fissano la definizione di
`setup_base_rate` — finestre da 28 giorni complete, titoli con prezzi, verso del
segnale — e le scelte che la rendono prudente.
"""
import json
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import Alert, OhlcvDaily, Stock, StockSetup
from app.models.stock_setup import STATUS_CONVERTED, STATUS_EXPIRED
from app.services import setup_base_rate as sbr
from app.services.setup_service import conversion_stats

OGGI = date(2026, 9, 16)
INIZIO = OGGI - timedelta(days=60)          # due finestre complete da 28 giorni


def _titoli(db, n: int) -> list[Stock]:
    out = []
    for i in range(n):
        s = Stock(ticker=f"BR{i}", exchange="NYSE", name=f"BR{i}", country="US")
        db.add(s)
        db.flush()
        # Una barra per finestra: il titolo e' «nell'universo» di entrambe.
        for giorno in (INIZIO + timedelta(days=5), INIZIO + timedelta(days=33)):
            db.add(OhlcvDaily(stock_id=s.id, date=giorno, open=1, high=1, low=1, close=1, volume=1))
        out.append(s)
    db.flush()
    return out


def _scatto(db, stock, giorno: date, tono: str = "bull", detector: str = "d", nata: date | None = None):
    snap = {"tone": tono}
    if nata is not None:
        snap["first_emitted_at"] = datetime(nata.year, nata.month, nata.day, 20, tzinfo=UTC).isoformat()
    db.add(Alert(stock_id=stock.id, signal_name=detector, signal_date=giorno,
                 trigger_price=1, snapshot=json.dumps(snap)))
    db.flush()


def test_la_quota_e_sui_titoli_finestra(db) -> None:
    t = _titoli(db, 10)
    _scatto(db, t[0], INIZIO + timedelta(days=3))
    _scatto(db, t[1], INIZIO + timedelta(days=10))
    _scatto(db, t[1], INIZIO + timedelta(days=12))       # stesso titolo, stessa finestra: uno
    _scatto(db, t[2], INIZIO + timedelta(days=40))
    _scatto(db, t[3], INIZIO + timedelta(days=41), tono="bear")
    db.commit()

    b = sbr.base_firing_rates(db, INIZIO, today=OGGI)
    assert b.windows == 2
    assert b.rates[("d", "bull")] == pytest.approx(3 / 20)
    assert b.rates[("d", "bear")] == pytest.approx(1 / 20)
    assert b.rates[("d", "any")] == pytest.approx(4 / 20)


def test_senza_una_finestra_completa_non_c_e_paragone(db) -> None:
    _titoli(db, 3)
    db.commit()
    assert sbr.base_firing_rates(db, OGGI - timedelta(days=20), today=OGGI) is None


def test_una_finestra_a_meta_non_entra(db) -> None:
    t = _titoli(db, 10)
    # Oltre la seconda finestra completa (giorno 56): la terza non e' finita.
    _scatto(db, t[0], INIZIO + timedelta(days=58))
    db.commit()
    b = sbr.base_firing_rates(db, INIZIO, today=OGGI)
    assert b.rates.get(("d", "bull"), 0) == 0


def test_una_catena_aggiornata_conta_anche_dove_e_nata(db) -> None:
    # La scansione ha spostato la data nella seconda finestra; lo scatto vero e'
    # nella prima. Senza `first_emitted_at` la prima finestra lo perderebbe.
    t = _titoli(db, 10)
    _scatto(db, t[0], INIZIO + timedelta(days=35), nata=INIZIO + timedelta(days=20))
    db.commit()
    b = sbr.base_firing_rates(db, INIZIO, today=OGGI)
    assert b.rates[("d", "bull")] == pytest.approx(2 / 20)


def test_il_paragone_si_pesa_sul_verso_dei_setup() -> None:
    b = sbr.BaseRates(
        rates={("d", "bull"): 0.20, ("d", "bear"): 0.10, ("d", "any"): 0.25},
        windows=2, first_day=INIZIO, last_day=OGGI,
    )
    assert b.for_tone_mix("d", {"bull": 3, "bear": 1}) == pytest.approx(0.175)
    # Un setup senza direzione accetta entrambi i versi: il suo paragone e' «any».
    assert b.for_tone_mix("d", {"undetermined": 2}) == pytest.approx(0.25)
    assert b.for_tone_mix("d", {}) is None
    assert b.for_tone_mix("sconosciuto", {"bull": 1}) == 0.0


def test_le_statistiche_portano_paragone_e_rapporto(db, monkeypatch) -> None:
    monkeypatch.setattr(
        sbr, "base_firing_rates",
        lambda _db, _primo, today=None: sbr.BaseRates(
            rates={("d", "bull"): 0.16, ("e", "bull"): 0.40},
            windows=3, first_day=INIZIO, last_day=OGGI,
        ),
    )
    s = _titoli(db, 1)[0]
    aperto = datetime(2026, 8, 1, tzinfo=UTC)
    for i, stato in enumerate([STATUS_CONVERTED] * 3 + [STATUS_EXPIRED] * 3):
        db.add(StockSetup(stock_id=s.id, detector="d", tone="bull", proximity=0.8, convenience=70,
                          missing="-", status=stato, shortlisted=True, closed_reason=None,
                          first_seen_at=aperto + timedelta(days=i), last_seen_at=aperto,
                          resolved_at=aperto + timedelta(days=10)))
    for stato in (STATUS_CONVERTED, STATUS_EXPIRED):
        db.add(StockSetup(stock_id=s.id, detector="e", tone="bull", proximity=0.8, convenience=70,
                          missing="-", status=stato, shortlisted=True,
                          first_seen_at=aperto, last_seen_at=aperto,
                          resolved_at=aperto + timedelta(days=10)))
    db.commit()

    st = conversion_stats(db)
    righe = {r["detector"]: r for r in st["by_detector"]}
    assert righe["d"]["base_rate_pct"] == 16.0
    assert righe["d"]["lift"] == pytest.approx(round(50.0 / 16.0, 1))
    assert righe["e"]["base_rate_pct"] == 40.0
    # Aggregato pesato sui chiusi di ogni tipo: (6*16 + 2*40) / 8 = 22.
    assert st["base_rate_pct"] == 22.0
    assert st["base_lift"] == pytest.approx(round(50.0 / 22.0, 1))
    assert st["base_windows"] == 3


def test_senza_paragone_i_campi_restano_vuoti(db) -> None:
    st = conversion_stats(db)
    assert st["base_rate_pct"] is None and st["base_lift"] is None
    assert st["base_windows"] == 0
