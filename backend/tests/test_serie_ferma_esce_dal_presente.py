"""Un titolo la cui serie si e' fermata non puo' sostenere un'affermazione al PRESENTE.

FA-071. La quarantena OHLCV del 2026-08-26 smise di scaricare i simboli morti e
di chiederne le quotazioni. Quella conoscenza non usci' pero' dall'ingestione, e
ogni consumatore che seleziona su `visible_country_clause()` da solo continuo' a
trattarli come vivi — la terza istanza della stessa forma, dopo la sweep delle
quotazioni e il percorso di lettura degli alert (FA-062).

Misurato in produzione il 2026-09-14, su 12 titoli morti di 1.010:

    Tecnico     BK 81,9 «Forte», CPRX 81,2, TERN 81,0 — al 98esimo percentile,
                calcolati OGGI su prezzi fermi da maggio e luglio
    Setup       9 aperti, 4 in shortlist con convenienza 78-84
    Alert       gli OTTO piu' revisionati dell'INTERO catalogo, fino a 372
                revisioni, con `triggered_at` spinto a oggi — e la lista
                ordina per `triggered_at` decrescente, quindi stavano in cima
                alla posta in arrivo ogni giorno

⚠️ Il punteggio alto non e' un caso: una serie ferma ha volatilita' nulla e
trend stabile, quindi produce un punteggio LUSINGHIERO. Un titolo morto non
finisce in fondo alla classifica, finisce in cima.
"""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models import Alert, OhlcvDaily, Stock, TechnicalScore
from app.models.stock_setup import (
    REASON_NO_DATA,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    StockSetup,
)
from app.services import ohlcv_service, scan_service, setup_service, technical_score_service

NOW = datetime.now(UTC)


def _titolo(db, ticker, *, streak=0, barre=21):
    s = Stock(
        ticker=ticker, exchange="NASDAQ", name=ticker, country="US",
        ohlcv_nodata_streak=streak,
        ohlcv_last_nodata_at=date.today() if streak else None,
    )
    db.add(s)
    db.flush()
    # Una figura di rottura: se il titolo viene valutato, un segnale nasce.
    for i in range(1, barre):
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 4, i),
                          open=100, high=101, low=99, close=100, volume=1000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 1),
                      open=100, high=112, low=100, close=110, volume=4000))
    db.commit()
    return s


def _setup_aperto(db, stock):
    row = StockSetup(
        stock_id=stock.id, detector="squeeze_expansion", tone="undetermined",
        proximity=0.7, convenience=80.0, missing="le bande devono riaprirsi",
        factors_json="{}", annotations_json="{}", status=STATUS_ACTIVE,
        first_seen_at=NOW - timedelta(days=2), last_seen_at=NOW,
        shortlisted=True,
    )
    db.add(row)
    db.commit()
    return row


# ── il predicato ────────────────────────────────────────────────────────────

def test_le_due_forme_del_predicato_concordano(db):
    """⚠️ Due copie della stessa regola in due linguaggi sono la forma che
    diverge — la nota che `not_quarantined_clause` porta gia', per lo stesso
    motivo. Qui si pretende che SQL e Python selezionino le stesse righe."""
    for streak in (0, 1, 2, 3, 99):
        _titolo(db, f"P{streak}", streak=streak, barre=3)

    da_sql = {
        t for (t,) in db.execute(
            select(Stock.ticker).where(ohlcv_service.series_stalled_clause())
        ).all()
    }
    da_python = {
        s.ticker for s in db.execute(select(Stock)).scalars().all()
        if ohlcv_service.series_is_stalled(s.ohlcv_nodata_streak)
    }
    assert da_sql == da_python
    # E il pavimento: senza, l'uguaglianza sarebbe vera anche di due insiemi
    # vuoti, cioe' di un predicato che non seleziona mai niente.
    assert da_sql == {"P3", "P99"}


# ── la guardia nella scansione ──────────────────────────────────────────────

def _spegni_i_cancelli(monkeypatch):
    for nome, val in (("signal_min_confidence", 0),
                      ("signal_require_follow_through", False),
                      ("signal_require_trend_alignment", False)):
        monkeypatch.setattr(f"app.signals.signal_scan_service.settings.{nome}", val)


def test_la_scansione_non_rivaluta_una_serie_ferma(db, monkeypatch):
    _spegni_i_cancelli(monkeypatch)
    vivo = _titolo(db, "VIVO", streak=0)
    morto = _titolo(db, "MORTO", streak=99)

    res = scan_service.scan_universe(db)
    db.commit()

    assert db.query(Alert).filter(Alert.stock_id == vivo.id).count() > 0
    # ⚠️ Il punto: valutare la barra congelata farebbe scattare il ramo di
    # aggiornamento in cooldown a ogni scansione, spingendo `triggered_at` a
    # oggi su un segnale di maggio.
    assert db.query(Alert).filter(Alert.stock_id == morto.id).count() == 0
    assert res.stocks_skipped >= 1


def test_la_scansione_toglie_il_punteggio_tecnico_di_una_serie_ferma(db, monkeypatch):
    _spegni_i_cancelli(monkeypatch)
    morto = _titolo(db, "EXFORTE", streak=99)
    # Il punteggio che una scansione precedente aveva calcolato quando il
    # titolo era ancora vivo: e' proprio la riga che restava in piedi.
    db.add(TechnicalScore(
        stock_id=morto.id, composite=81.9, posture="Forte",
        computed_at=NOW, breakdown="{}",
    ))
    db.commit()

    scan_service.scan_universe(db)
    db.commit()

    assert db.query(TechnicalScore).filter(TechnicalScore.stock_id == morto.id).count() == 0


def test_il_punteggio_di_un_titolo_VIVO_non_viene_toccato(db, monkeypatch):
    """Controllo negativo. `forget` riceve una lista esplicita e mai «tutti
    quelli fuori da partials»: la scansione salta titoli anche per storia
    troppo corta, e cancellare per esclusione svuoterebbe la classifica."""
    _spegni_i_cancelli(monkeypatch)
    corto = _titolo(db, "CORTO", streak=0, barre=2)  # saltato: storia insufficiente
    db.add(TechnicalScore(
        stock_id=corto.id, composite=50.0, posture="Neutro",
        computed_at=NOW, breakdown="{}",
    ))
    db.commit()

    scan_service.scan_universe(db)
    db.commit()

    assert db.query(TechnicalScore).filter(TechnicalScore.stock_id == corto.id).count() == 1


def test_forget_non_cancella_cio_che_non_gli_e_stato_chiesto(db):
    a = _titolo(db, "FA", streak=99, barre=3)
    b = _titolo(db, "FB", streak=99, barre=3)
    for s in (a, b):
        db.add(TechnicalScore(stock_id=s.id, composite=70.0, posture="Forte",
                              computed_at=NOW, breakdown="{}"))
    db.commit()

    assert technical_score_service.forget(db, [a.id]) == 1
    db.commit()
    rimasti = {r.stock_id for r in db.query(TechnicalScore).all()}
    assert rimasti == {b.id}
    # Una lista vuota non e' «tutti».
    assert technical_score_service.forget(db, []) == 0


# ── la quarta ragione di chiusura ───────────────────────────────────────────

def test_un_setup_su_serie_ferma_si_chiude_per_DATI_non_per_decadenza(db):
    """⚠️ La ragione conta quanto la chiusura.

    `stale` significa «le condizioni si sono sfaldate»: detto di un titolo che
    ha smesso di quotare e' falso, e falso nel modo peggiore — non sono
    decadute, abbiamo smesso di poterle osservare.
    """
    morto = _titolo(db, "SETMORTO", streak=99, barre=3)
    row = _setup_aperto(db, morto)

    assert setup_service.close_setups_without_data(db) == 1
    db.commit()
    db.refresh(row)
    assert row.status == STATUS_EXPIRED
    assert row.closed_reason == REASON_NO_DATA
    assert row.resolved_at is not None


def test_un_setup_su_un_titolo_VIVO_resta_aperto(db):
    """Controllo positivo all'incontrario: senza, il test sopra sarebbe vero
    anche di una funzione che chiude tutto."""
    vivo = _titolo(db, "SETVIVO", streak=0, barre=3)
    row = _setup_aperto(db, vivo)

    assert setup_service.close_setups_without_data(db) == 0
    db.commit()
    db.refresh(row)
    assert row.status == STATUS_ACTIVE
    assert row.closed_reason is None
