"""Gli avvisi sulle posizioni eToro aperte (FA-146)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import settings
from app.models import EtoroPosizione, EtoroStrumento, OhlcvDaily, Stock
from app.services import allarmi_posizioni_service as ap
from app.services import notifier_service

ADESSO = datetime(2026, 11, 16, 16, 0, tzinfo=UTC)   # lunedi', seduta USA aperta


# ─── La valutazione, pura ──────────────────────────────────────────────────

def test_lo_stop_vicino_scatta_dentro_la_soglia_e_non_oltre_lo_stop():
    base = dict(chiusura_prec=None, atr=2.0, soglia_stop_atr=0.5, soglia_mossa_atr=2.0)
    assert "stop_vicino" in ap.valuta(prezzo=100.9, stop=100.0, lato="long", **base)
    assert ap.valuta(prezzo=101.1, stop=100.0, lato="long", **base) == {}
    # Oltre lo stop la posizione si chiude: lo dice la notifica di chiusura.
    assert ap.valuta(prezzo=99.0, stop=100.0, lato="long", **base) == {}
    assert "stop_vicino" in ap.valuta(prezzo=99.2, stop=100.0, lato="short", **base)
    assert ap.valuta(prezzo=100.9, stop=None, lato="long", **base) == {}


def test_la_mossa_anomala_si_misura_in_atr_nei_due_versi():
    base = dict(stop=None, lato="long", atr=2.0, soglia_stop_atr=0.5, soglia_mossa_atr=2.0)
    giu = ap.valuta(prezzo=95.9, chiusura_prec=100.0, **base)["mossa"]
    assert giu["variazione_atr"] == pytest.approx(-2.05)
    assert "mossa" in ap.valuta(prezzo=104.0, chiusura_prec=100.0, **base)
    assert ap.valuta(prezzo=103.9, chiusura_prec=100.0, **base) == {}
    assert ap.valuta(prezzo=90.0, chiusura_prec=100.0, **{**base, "atr": None}) == {}


# ─── Lettura dal database ──────────────────────────────────────────────────

def _posizione(db, *, prezzo=100.9, stop=100.0, pnl_il=ADESSO - timedelta(minutes=5)):
    s = Stock(ticker="SOXL", exchange="NYSE", name="Direxion", country="US")
    db.add(s)
    db.flush()
    for i in range(30):
        c = 100.0 + (i % 2)    # range 1-2: ATR circa 2
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 10, 1) + timedelta(days=i), open=c,
                          high=c + 1, low=c - 1, close=c, volume=1e6))
    db.add(EtoroStrumento(instrument_id=1, simbolo="SOXL", stock_id=s.id, abbinamento="auto",
                          aggiornato_il=ADESSO))
    db.flush()
    db.add(EtoroPosizione(position_id=7, instrument_id=1, lato="long", leva=5, regolamento="cfd",
                          aperta_il=ADESSO - timedelta(days=20), prezzo_apertura=110.0, unita=1,
                          importo_usd=100.0, stop=stop, prezzo_corrente=prezzo, pnl_il=pnl_il,
                          vista_il=ADESSO))
    db.commit()


def _avvisi(db, **kw):
    return ap.da_avvisare(db, soglia_stop_atr=0.5, soglia_mossa_atr=20.0, adesso=ADESSO,
                          aperto=kw.pop("aperto", lambda t: True))


def test_un_avviso_al_giorno_per_posizione_e_tipo(db):
    _posizione(db)
    avvisi = _avvisi(db)
    assert [(a.ticker, a.tipo) for a in avvisi] == [("SOXL", "stop_vicino")]
    ap.segna(db, avvisi, ADESSO.date())
    assert _avvisi(db) == []
    domani = ap.da_avvisare(db, soglia_stop_atr=0.5, soglia_mossa_atr=20.0,
                            adesso=ADESSO + timedelta(days=1), aperto=lambda t: True)
    # Il giorno dopo il prezzo di eToro e' vecchio: niente. Con un prezzo fresco si.
    assert domani == []


def test_a_mercato_chiuso_o_col_prezzo_vecchio_niente(db):
    _posizione(db, pnl_il=ADESSO - timedelta(hours=3))
    assert _avvisi(db) == []


def test_a_borsa_usa_chiusa_niente(db):
    _posizione(db)
    assert _avvisi(db, aperto=lambda t: False) == []


# ─── Notifica e job ────────────────────────────────────────────────────────

def _avviso():
    return ap.Avviso(position_id=7, ticker="SOXL", tipo="stop_vicino", lato="long", prezzo=100.9,
                     stop=100.0, distanza_pct=0.009, distanza_atr=0.45, variazione_pct=None,
                     variazione_atr=None)


def test_la_notifica_dice_distanza_e_si_spegne(monkeypatch):
    testi = []
    monkeypatch.setattr(notifier_service, "_telegram_enabled", lambda: True)
    monkeypatch.setattr(notifier_service, "_send_telegram", lambda t, what: testi.append(t) or True)
    monkeypatch.setattr(settings, "telegram_posizioni", True)
    assert notifier_service.notify_posizioni([_avviso()]).sent
    assert "SOXL" in testi[0] and "0.45 ATR dallo stop" in testi[0]
    monkeypatch.setattr(settings, "telegram_posizioni", False)
    assert notifier_service.notify_posizioni([_avviso()]).reason == "push_disabled"


def test_il_job_segna_solo_dopo_un_invio_riuscito(db, monkeypatch):
    from app.scheduler.jobs import sincronizza_etoro as job

    segnati = []
    monkeypatch.setattr(settings, "telegram_posizioni", True)
    monkeypatch.setattr(ap, "da_avvisare", lambda *a, **k: [_avviso()])
    monkeypatch.setattr(ap, "segna", lambda d, avvisi, g: segnati.append(len(avvisi)))
    esito = {"sent": False}
    monkeypatch.setattr(notifier_service, "notify_posizioni",
                        lambda a: type("R", (), {"sent": esito["sent"]})())
    job._avvisa_posizioni(db)
    assert segnati == []
    esito["sent"] = True
    job._avvisa_posizioni(db)
    assert segnati == [1]
    monkeypatch.setattr(settings, "telegram_posizioni", False)
    job._avvisa_posizioni(db)
    assert segnati == [1]


def test_l_orario_di_mercato_vale_per_i_titoli_usa(monkeypatch):
    from app.services import premarket_service

    monkeypatch.setattr(premarket_service, "us_market_open_now", lambda: False)
    assert ap.mercato_aperto("SOXL") is False
    assert ap.mercato_aperto("ENI.MI") is True     # fuori USA decide la freschezza
    monkeypatch.setattr(premarket_service, "us_market_open_now", lambda: True)
    assert ap.mercato_aperto("SOXL") is True
