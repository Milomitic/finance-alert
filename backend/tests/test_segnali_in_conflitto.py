"""Segnali in conflitto (FA-151): stesso titolo, verso opposto, nati entro un giorno.

199 coppie titolo-giorno in produzione avevano un alert rialzista e uno
ribassista, e lo schermo li mostrava come due segnali indipendenti.
"""
import json
from datetime import UTC, datetime

from app.models import Alert, Stock
from app.services import alert_service
from app.services.signal_breadth_service import conflitti_per, tone_of


def _stock(db, ticker="ACME"):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker)
    db.add(s)
    db.commit()
    return s


def _alert(db, s, tono, nato, nome="trend_pullback"):
    a = Alert(stock_id=s.id, signal_name=nome, trigger_price=10.0,
              triggered_at=nato, snapshot=json.dumps({"tone": tono, "first_emitted_at": nato.isoformat()}))
    db.add(a)
    db.commit()
    return a


def _c(db, *alerts):
    return conflitti_per(db, [(a.id, a.stock_id, tone_of(a), a.emitted_at) for a in alerts])


G = datetime(2026, 11, 10, 22, 0, tzinfo=UTC)


def test_verso_opposto_entro_un_giorno_e_conflitto_nei_due_sensi(db):
    s = _stock(db)
    su = _alert(db, s, "bull", G)
    giu = _alert(db, s, "bear", G.replace(day=11), nome="structure_break")
    c = _c(db, su, giu)
    assert c[su.id].alert_id == giu.id and c[su.id].signal_name == "structure_break"
    assert c[giu.id].alert_id == su.id and c[giu.id].tone == "bull"


def test_stesso_verso_lontano_nel_tempo_o_altro_titolo_no(db):
    s, altro = _stock(db), _stock(db, "OTHER")
    su = _alert(db, s, "bull", G)
    _alert(db, s, "bull", G, nome="sr_flip")                      # stesso verso
    _alert(db, s, "bear", G.replace(day=13))                      # tre giorni dopo
    _alert(db, altro, "bear", G)                                  # altro titolo
    assert _c(db, su) == {}


def test_undetermined_non_entra_ne_come_alert_ne_come_controparte(db):
    s = _stock(db)
    su = _alert(db, s, "bull", G)
    nd = _alert(db, s, "undetermined", G, nome="squeeze_expansion")
    assert _c(db, su, nd) == {}


def test_conta_la_NASCITA_non_la_revisione(db):
    """Due segnali vivi insieme non sono in conflitto se sono nati lontani:
    `triggered_at` avanza a ogni revisione e li farebbe coincidere."""
    s = _stock(db)
    vecchio = _alert(db, s, "bull", G.replace(day=1))
    vecchio.triggered_at = G           # rivisto oggi
    db.commit()
    nuovo = _alert(db, s, "bear", G)
    assert _c(db, nuovo) == {}


def test_il_piu_vicino_vince_e_gli_archiviati_contano(db):
    s = _stock(db)
    su = _alert(db, s, "bull", G)
    lontano = _alert(db, s, "bear", G.replace(day=9))
    vicino = _alert(db, s, "bear", G.replace(hour=23))
    vicino.archived_at = G
    db.commit()
    assert _c(db, su)[su.id].alert_id == vicino.id
    assert lontano.id != vicino.id


def test_la_lista_e_il_dettaglio_portano_il_campo(db):
    s = _stock(db)
    su = _alert(db, s, "bull", G)
    giu = _alert(db, s, "bear", G)
    items, *_ = alert_service.list_alerts(db, archived=None)
    per_id = {i["id"]: i for i in items}
    assert per_id[su.id]["in_conflitto_con"]["alert_id"] == giu.id
    assert alert_service.get_alert_detail(db, giu.id)["in_conflitto_con"]["alert_id"] == su.id


def test_nel_digest_la_coppia_e_una_riga(db, monkeypatch):
    from app.services import notifier_service, rilevanza_service

    s, altro = _stock(db), _stock(db, "OTHER")
    su = _alert(db, s, "bull", G, nome="trend_pullback")
    giu = _alert(db, s, "bear", G, nome="structure_break")
    solo = _alert(db, altro, "bull", G)
    monkeypatch.setattr(rilevanza_service, "titoli_rilevanti",
                        lambda d: {s.id: "posizione", altro.id: "preferito"})
    voci = notifier_service._unisci_conflitti([su, solo, giu])
    assert voci == [(su, giu), solo]
    testo = notifier_service.build_digest_message(db, [su, solo, giu])
    righe = [r for r in testo.splitlines() if "ACME" in r]
    assert len(righe) == 1 and "in conflitto" in righe[0]
