"""FA-164: gli esiti gia' maturati si riallineano ai dati di oggi.

Le barre salvate vengono riscritte dopo la maturazione (riscaricamento
dell'ultimo mese, buchi riparati, split): un esito fissato una volta
fotografa uno stato poi corretto. Misurato in produzione il 2026-11-14: il
90% delle mediane non si riproduceva piu'."""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import select, update

from app.core.provenance import OUTCOME_METHOD_VERSION
from app.models import Alert, EsitoOrizzonte, OhlcvDaily, SignalCandidate, SignalOutcome, Stock
from app.services import esiti_orizzonti_service as eo
from app.services import signal_outcome_service as sos

D0 = date(2026, 1, 5)


def _seme(db, n=40):
    titoli = []
    for k in range(n):
        s = Stock(ticker=f"R{k:02d}", exchange="NASDAQ", name=f"R {k}", country="US")
        db.add(s)
        db.flush()
        for i in range(60):
            c = 50.0 + k + i * (0.1 + k / 100)
            db.add(OhlcvDaily(stock_id=s.id, date=D0 + timedelta(days=i), open=c, high=c,
                              low=c, close=c, volume=1e6))
        titoli.append(s)
    a = Alert(stock_id=titoli[0].id, trigger_price=1.0, signal_name="trend_pullback",
              signal_date=D0 + timedelta(days=30),
              snapshot=json.dumps({"tone": "bull",
                                   "first_emitted_at": f"{D0 + timedelta(days=30)}T23:30:00+00:00"}))
    db.add(a)
    db.add(SignalCandidate(stock_id=titoli[1].id, detector="trend_pullback", tone="bear",
                           signal_date=D0 + timedelta(days=30), bar_date=D0 + timedelta(days=30),
                           close=1.0, strength=55, passa_forza=False, passa_trend=True,
                           passa_follow=True))
    db.commit()
    return titoli, a


def _correggi(db, stock_id: int, giorno: int, fattore: float) -> None:
    db.execute(update(OhlcvDaily).where(
        OhlcvDaily.stock_id == stock_id, OhlcvDaily.date == D0 + timedelta(days=giorno),
    ).values(close=OhlcvDaily.close * fattore))
    db.commit()


def test_una_barra_corretta_dopo_la_maturazione_cambia_l_esito(db, monkeypatch):
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 5)
    titoli, a = _seme(db)
    sos.mature_outcomes(db)
    sos.mature_candidate_outcomes(db)
    o = db.execute(select(SignalOutcome)).scalars().one()
    c = db.execute(select(SignalCandidate)).scalars().one()
    prima_alert, prima_scartato = o.fwd_return, c.fwd_return
    # Nessun cambiamento nei dati: niente da riallineare.
    assert sos.riallinea_esiti(db)["alert_cambiati"] == 0

    # La barra d'uscita di entrambi viene corretta, come farebbe un riscaricamento.
    _correggi(db, titoli[0].id, 35, 0.9)
    _correggi(db, titoli[1].id, 35, 1.1)
    out = sos.riallinea_esiti(db)
    assert (out["alert_cambiati"], out["scartati_cambiati"]) == (1, 1)
    db.refresh(o)
    db.refresh(c)
    assert o.fwd_return < prima_alert and c.fwd_return > prima_scartato
    assert o.method_version == OUTCOME_METHOD_VERSION
    # Il secondo passaggio non trova piu' niente: tocca solo cio' che cambia.
    assert sos.riallinea_esiti(db)["alert_cambiati"] == 0


def test_le_righe_del_replay_non_si_toccano(db, monkeypatch):
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 5)
    titoli, a = _seme(db)
    sos.mature_outcomes(db)
    db.execute(update(SignalOutcome).values(source="replay"))
    db.commit()
    _correggi(db, titoli[0].id, 35, 0.9)
    assert sos.riallinea_esiti(db)["alert_esaminati"] == 0


def test_gli_orizzonti_si_riallineano_con_lo_stesso_calcolo(db):
    titoli, a = _seme(db)
    eo.matura(db, eta_massima_giorni=None)
    righe = {r.orizzonte: r.rendimento for r in db.execute(select(EsitoOrizzonte)).scalars()}
    assert eo.riallinea(db) == (len(righe), 0)
    _correggi(db, titoli[0].id, 35, 0.9)     # uscita a 5 sedute
    esaminate, cambiate = eo.riallinea(db)
    assert esaminate == len(righe) and cambiate >= 1
    dopo = {r.orizzonte: r.rendimento for r in db.execute(select(EsitoOrizzonte)).scalars()}
    assert dopo[5] < righe[5] and dopo[1] == righe[1]
    assert eo.riallinea(db)[1] == 0


def test_il_job_salta_durante_una_scansione_e_altrimenti_riallinea(db, monkeypatch):
    import app.core.db as dbm
    from app.scheduler.jobs import riallinea_esiti as job
    from app.services import scan_lock

    chiamate = []
    monkeypatch.setattr(sos, "riallinea_esiti", lambda d: chiamate.append("alert"))
    monkeypatch.setattr(eo, "riallinea", lambda d: chiamate.append("orizzonti"))
    monkeypatch.setattr(dbm, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    monkeypatch.setattr(scan_lock, "is_running", lambda: True)
    job.run_riallinea_esiti()
    assert chiamate == []
    monkeypatch.setattr(scan_lock, "is_running", lambda: False)
    job.run_riallinea_esiti()
    assert chiamate == ["alert", "orizzonti"]


# ─── Il contratto del conteggio e del commit ──────────────────────────────
# Trovati dalla sonda di mutazione: senza questi, un contatore sbagliato, un
# ritorno anticipato con una sola delle due liste o un commit mancato
# passavano tutti.

def test_il_conteggio_degli_esaminati_e_esatto(db, monkeypatch):
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 5)
    _seme(db)
    sos.mature_outcomes(db)
    sos.mature_candidate_outcomes(db)
    assert sos.riallinea_esiti(db) == {
        "alert_esaminati": 1, "alert_cambiati": 0,
        "scartati_esaminati": 1, "scartati_cambiati": 0,
    }


def test_con_i_soli_alert_si_riallinea_e_si_salva(db, monkeypatch):
    """Nessuno scartato: il ritorno anticipato vale solo se mancano ENTRAMBI,
    e il commit parte anche se e' cambiato uno solo dei due."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 5)
    titoli, _a = _seme(db)
    db.query(SignalCandidate).delete()
    db.commit()
    sos.mature_outcomes(db)
    o = db.execute(select(SignalOutcome)).scalars().one()
    prima = o.fwd_return
    _correggi(db, titoli[0].id, 35, 0.9)
    out = sos.riallinea_esiti(db)
    assert (out["alert_cambiati"], out["scartati_esaminati"]) == (1, 0)
    db.rollback()                  # cio' che non e' stato salvato sparisce qui
    db.refresh(o)
    assert o.fwd_return < prima


def test_senza_commit_non_si_salva(db, monkeypatch):
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 5)
    titoli, _a = _seme(db)
    sos.mature_outcomes(db)
    sos.mature_candidate_outcomes(db)
    o = db.execute(select(SignalOutcome)).scalars().one()
    prima = o.fwd_return
    _correggi(db, titoli[0].id, 35, 0.9)
    assert sos.riallinea_esiti(db, commit=False)["alert_cambiati"] == 1
    db.rollback()
    db.refresh(o)
    assert o.fwd_return == prima


def test_un_valore_che_compare_o_sparisce_e_un_cambiamento():
    """Un esito che prima non c'era (o non c'e' piu') e' un cambiamento, e due
    assenze no. Con un solo None il confronto numerico solleverebbe."""
    assert sos._cambiato(None, 0.1) is True
    assert sos._cambiato(0.1, None) is True
    assert sos._cambiato(None, None) is False
    assert sos._cambiato(0.1, 0.1) is False
    assert sos._cambiato(0.1, 0.2) is True
