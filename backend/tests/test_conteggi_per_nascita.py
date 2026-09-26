"""I conteggi degli alert contano le NASCITE, non le revisioni (FA-100).

Un alert e' una riga viva: finche' il segnale persiste, ogni scansione lo
rivede e riscrive `triggered_at`. Ogni conteggio «alert nelle ultime N ore»
costruito su quel campo contava quindi anche tutti i segnali nati prima e
ancora vivi. Misurato il 2026-09-26: digest del 24/09 «723 alert» contro 87
nati nella finestra, del 25/09 «568» contro 66; KPI del cruscotto 555 contro 71.

`Alert.emitted_at` e' la nascita, indicizzata: scritta alla creazione e mai
piu' toccata. Il modello la ricava da `snapshot.first_emitted_at`, col ripiego
su `triggered_at` — la stessa regola con cui la migrazione ha riempito lo
storico, cosi' colonna e snapshot non possono divergere.

⚠️ Ogni test porta il suo controllo negativo: lo stesso conteggio fatto
sull'ultima revisione deve dare un numero DIVERSO. Senza, una fixture in cui
nascita e revisione coincidono renderebbe ogni asserzione vera di niente.
"""
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Alert, Index, ScanRun, Stock, StockIndex

ORA = datetime.now(UTC)


def _utc(dt: datetime) -> datetime:
    """SQLite rende i DateTime senza fuso: la convenzione del progetto e' UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _titolo(db, ticker: str = "AAA") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Corp", country="US")
    db.add(s)
    db.flush()
    return s


def _alert(db, stock: Stock, *, nato: datetime, rivisto: datetime | None = None,
           signal_name: str = "volume_breakout", prezzo_nascita: float | None = None,
           prezzo_ora: float = 100.0) -> Alert:
    """Un alert nato a `nato` e, se `rivisto`, rivisto l'ultima volta allora —
    come lo lascia la scansione: `triggered_at` e `trigger_price` avanzano,
    `first_emitted_at` e `first_price` restano quelli della nascita."""
    snap = {"tone": "bull", "strength": 70, "chain": [],
            "first_emitted_at": nato.isoformat()}
    if prezzo_nascita is not None:
        snap["first_price"] = prezzo_nascita
    a = Alert(
        stock_id=stock.id, signal_name=signal_name, trigger_price=prezzo_ora,
        signal_date=(rivisto or nato).date(), snapshot=json.dumps(snap),
        triggered_at=rivisto or nato,
    )
    db.add(a)
    db.flush()
    return a


def _contati_sulla_revisione(db, dopo: datetime) -> int:
    """Il conteggio come lo faceva il codice prima di FA-100."""
    return db.scalar(select(func.count(Alert.id)).where(Alert.triggered_at > dopo))


# ── la regola della nascita, sul modello ──────────────────────────────────


def test_la_nascita_e_first_emitted_at_non_l_ultima_revisione(db):
    a = _alert(db, _titolo(db), nato=ORA - timedelta(days=3),
               rivisto=ORA - timedelta(hours=2))
    db.commit()
    db.refresh(a)
    assert _utc(a.emitted_at) == ORA - timedelta(days=3)
    assert _utc(a.triggered_at) == ORA - timedelta(hours=2)


def test_senza_first_emitted_at_la_nascita_e_triggered_at(db):
    """Gli alert di prezzo, e quelli che precedono il campo: una riga mai
    rivista e' nata quando e' stata scritta."""
    s = _titolo(db)
    a = Alert(stock_id=s.id, trigger_price=10.0, snapshot="{}",
              triggered_at=ORA - timedelta(days=2))
    db.add(a)
    db.commit()
    db.refresh(a)
    assert _utc(a.emitted_at) == ORA - timedelta(days=2)


def test_senza_nessuno_dei_due_la_nascita_e_adesso(db):
    s = _titolo(db)
    a = Alert(stock_id=s.id, trigger_price=10.0, snapshot="{}")
    db.add(a)
    db.commit()
    db.refresh(a)
    assert abs(_utc(a.emitted_at) - datetime.now(UTC)) < timedelta(minutes=1)


def test_un_first_emitted_at_illeggibile_ripiega_su_triggered_at(db):
    s = _titolo(db)
    rotto = Alert(stock_id=s.id, trigger_price=10.0,
                  snapshot=json.dumps({"first_emitted_at": "ieri sera"}),
                  triggered_at=ORA - timedelta(days=4))
    non_json = Alert(stock_id=s.id, trigger_price=10.0, snapshot="{non e' json",
                     triggered_at=ORA - timedelta(days=5))
    db.add_all([rotto, non_json])
    db.commit()
    assert _utc(rotto.emitted_at) == ORA - timedelta(days=4)
    assert _utc(non_json.emitted_at) == ORA - timedelta(days=5)


def test_un_istante_con_un_altro_fuso_si_porta_in_UTC(db):
    """SQLite scrive l'ora del quadrante e butta il fuso: senza la conversione
    un'emissione alle 01:30 di Roma diventerebbe le 01:30 UTC, due ore dopo."""
    s = _titolo(db)
    a = Alert(stock_id=s.id, trigger_price=10.0,
              snapshot=json.dumps({"first_emitted_at": "2026-09-25T01:30:00+02:00"}))
    db.add(a)
    db.commit()
    db.refresh(a)
    assert _utc(a.emitted_at) == datetime(2026, 9, 24, 23, 30, tzinfo=UTC)


def test_una_revisione_non_sposta_la_nascita(db):
    a = _alert(db, _titolo(db), nato=ORA - timedelta(days=3))
    db.commit()
    a.triggered_at = ORA
    a.trigger_price = 120.0
    db.commit()
    db.refresh(a)
    assert _utc(a.emitted_at) == ORA - timedelta(days=3)


# ── i conteggi ────────────────────────────────────────────────────────────


def test_il_KPI_delle_24_ore_conta_le_NASCITE(db):
    from app.services.stats_service import get_kpi_summary

    s = _titolo(db)
    _alert(db, s, nato=ORA - timedelta(hours=2))
    _alert(db, s, nato=ORA - timedelta(days=3), rivisto=ORA - timedelta(hours=1))
    _alert(db, s, nato=ORA - timedelta(hours=30), rivisto=ORA - timedelta(hours=3))
    db.commit()

    k = get_kpi_summary(db)
    assert k.alerts_last_24h == 1
    assert k.alerts_prev_24h == 1
    # Controllo negativo: sull'ultima revisione sarebbero tre nelle 24 ore.
    assert _contati_sulla_revisione(db, ORA - timedelta(hours=24)) == 3


def test_il_grafico_per_giorno_mette_l_alert_nel_giorno_in_cui_e_nato(db):
    from app.services.stats_service import get_alerts_by_day

    nato = datetime.combine(ORA.date() - timedelta(days=3), datetime.min.time(),
                            tzinfo=UTC) + timedelta(hours=12)
    _alert(db, _titolo(db), nato=nato, rivisto=ORA - timedelta(minutes=5))
    db.commit()

    punti = {p.date: p.count for p in get_alerts_by_day(db, days=7)}
    assert punti[nato.date()] == 1
    assert sum(punti.values()) == 1


def test_per_indice_per_titolo_e_della_settimana_contano_le_nascite(db):
    from app.services.stats_service import (
        get_alerts_by_index,
        get_top_alerted_stock_7d,
        get_top_stocks,
    )

    s = _titolo(db)
    idx = Index(code="SP500", name="S&P 500")
    db.add(idx)
    db.flush()
    db.add(StockIndex(stock_id=s.id, index_id=idx.id))
    # Nato 35 giorni fa, rivisto 10 giorni fa: dentro il tetto di 28 giorni
    # della catena, quindi una storia possibile.
    _alert(db, s, nato=ORA - timedelta(days=35), rivisto=ORA - timedelta(days=10))
    # Nato 10 giorni fa, rivisto ieri.
    _alert(db, s, nato=ORA - timedelta(days=10), rivisto=ORA - timedelta(days=1))
    db.commit()

    assert [p.alert_count for p in get_alerts_by_index(db, days=30)] == [1]
    assert [t.alert_count for t in get_top_stocks(db, days=30)] == [1]
    assert get_top_alerted_stock_7d(db) is None
    assert _contati_sulla_revisione(db, ORA - timedelta(days=7)) == 1


def test_il_digest_conta_le_nascite_e_mostra_il_prezzo_d_ingresso(db):
    from app.services.notifier_service import _fetch_alerts_last_24h, build_digest_message

    s = _titolo(db, "NUOVO")
    nuovo = _alert(db, s, nato=ORA - timedelta(hours=2), rivisto=ORA - timedelta(hours=1),
                   prezzo_nascita=50.0, prezzo_ora=55.0)
    _alert(db, _titolo(db, "VECCHIO"), nato=ORA - timedelta(days=3),
           rivisto=ORA - timedelta(hours=1))
    db.commit()

    alerts = _fetch_alerts_last_24h(db)
    assert [a.id for a in alerts] == [nuovo.id]
    assert _contati_sulla_revisione(db, ORA - timedelta(hours=24)) == 2

    testo = build_digest_message(db, alerts)
    assert "<b>1 nuovo alert</b>" in testo
    # Il prezzo a cui e' comparso, non quello dell'ultima revisione: e' lo
    # stesso numero che la lista mostra come ingresso.
    assert "(50)" in testo and "(55)" not in testo
    assert (ORA - timedelta(hours=2)).strftime("%H:%M") in testo


def test_la_classifica_conta_i_segnali_nati_nella_finestra(db):
    from app.services.leaderboard_service import _signal_counts

    s = _titolo(db)
    _alert(db, s, nato=ORA - timedelta(days=35), rivisto=ORA - timedelta(days=10))
    _alert(db, s, nato=ORA - timedelta(days=5), signal_name="sr_flip")
    db.commit()

    conti = _signal_counts(db, days=30)
    assert conti[s.id].bull == 1
    assert _contati_sulla_revisione(db, ORA - timedelta(days=30)) == 2


def test_gli_alert_di_una_scansione_sono_quelli_NATI_mentre_girava(db):
    from app.api.platform_health import _recent_scans

    s = _titolo(db)
    inizio, fine = ORA - timedelta(hours=1), ORA - timedelta(minutes=50)
    db.add(ScanRun(trigger="cron", status="success", started_at=inizio, completed_at=fine))
    _alert(db, s, nato=ORA - timedelta(minutes=55))
    _alert(db, s, nato=ORA - timedelta(days=3), rivisto=ORA - timedelta(minutes=55),
           signal_name="sr_flip")
    db.commit()

    (scan,) = _recent_scans(db)
    assert scan.alerts_count == 1
    assert _contati_sulla_revisione(db, inizio) == 2


def test_il_filtro_per_data_della_lista_legge_la_nascita(db):
    """La lista mostra il giorno di nascita e ci si ordina sopra: il filtro
    «Oggi» deve parlare dello stesso giorno, non dell'ultima revisione."""
    from app.services.alert_service import list_alerts

    oggi = ORA.date()
    inizio_giornata = datetime.combine(oggi, datetime.min.time(), tzinfo=UTC)
    # `max(inizio_giornata, ...)`: tiene entrambe le date dentro OGGI anche se
    # il test gira nei primi minuti dopo la mezzanotte UTC.
    nuovo = _alert(db, _titolo(db, "NUOVO"), nato=max(inizio_giornata, ORA - timedelta(minutes=10)))
    _alert(db, _titolo(db, "VECCHIO"), nato=ORA - timedelta(days=3),
           rivisto=max(inizio_giornata, ORA - timedelta(minutes=5)))
    db.commit()

    items, total, _ = list_alerts(db, date_from=oggi)
    assert [i["id"] for i in items] == [nuovo.id] and total == 1

    # Il limite superiore e' esclusivo, e sulla stessa colonna.
    items, _, _ = list_alerts(db, date_from=oggi - timedelta(days=4), date_to=oggi)
    assert [i["ticker"] for i in items] == ["VECCHIO"]
    assert _contati_sulla_revisione(db, inizio_giornata - timedelta(microseconds=1)) == 2

