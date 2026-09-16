"""Un setup converte nel SUO evento, e l'evento resta fermo (2026-09-16).

Tre difetti misurati in produzione, ognuno fissato qui:

- la conversione stava solo sul ramo che CREA un alert: 95 setup restavano
  attivi con la condizione gia' scattata, tutti passati dal ramo che aggiorna;
- il setup puntava a un alert vivo: 71 conversioni su 334 misuravano l'esito
  da una data scivolata fino a 28 giorni oltre la conversione;
- la conversione non guardava il verso: 68 su 334 erano eventi opposti.
"""
import json
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.models import Alert, OhlcvDaily, SignalOutcome, Stock, StockSetup
from app.models.stock_setup import (
    CONVERSION_LEGACY,
    CONVERSION_LIVE,
    CONVERSION_RECONCILED,
    REASON_DECAYED,
    REASON_MISLINKED,
    STATUS_ACTIVE,
    STATUS_CONVERTED,
    STATUS_EXPIRED,
)
from app.services import setup_service, signal_outcome_service
from app.signals.signal_scan_service import evaluate_signals

_SEQ = {"n": 0}


def _stock(db) -> Stock:
    _SEQ["n"] += 1
    s = Stock(ticker=f"EV{_SEQ['n']}", exchange="NYSE", name="Ev", country="US")
    db.add(s)
    db.flush()
    return s


def _setup(db, stock, *, tone="bull", detector="volume_breakout", bar=date(2026, 9, 11),
           status=STATUS_ACTIVE, **kw) -> StockSetup:
    row = StockSetup(
        stock_id=stock.id, detector=detector, tone=tone, proximity=0.8,
        convenience=70.0, missing="-", status=status, shortlisted=True,
        first_seen_at=datetime(bar.year, bar.month, bar.day, 20, tzinfo=UTC),
        last_seen_at=datetime.now(UTC), first_seen_bar=bar, **kw,
    )
    db.add(row)
    db.flush()
    return row


def _alert(db, stock, *, giorno=date(2026, 9, 15), tone="bull",
           detector="volume_breakout") -> Alert:
    a = Alert(stock_id=stock.id, signal_name=detector, signal_date=giorno,
              trigger_price=50.0, snapshot=json.dumps({"tone": tone}))
    db.add(a)
    db.flush()
    return a


def _converti(db, alert, *, giorno=date(2026, 9, 15), tone="bull", price=50.0):
    return setup_service.convert_setups_for_event(
        db, alert, signal_date=giorno, tone=tone, price=price,
    )


# --- La regola -------------------------------------------------------------

def test_converte_su_una_barra_successiva_e_registra_l_evento(db) -> None:
    s = _stock(db)
    row = _setup(db, s, bar=date(2026, 9, 11))
    a = _alert(db, s)
    assert _converti(db, a, price=51.5) is row
    assert row.status == STATUS_CONVERTED
    assert row.conversion_source == CONVERSION_LIVE
    assert row.converted_alert_id == a.id
    assert row.converted_signal_date == date(2026, 9, 15)
    assert row.converted_price == 51.5
    assert row.converted_tone == "bull"
    # Anticipo sul MERCATO: dalla barra d'apertura alla barra dell'evento.
    assert row.bar_lead_days == 4


def test_la_barra_di_apertura_non_basta(db) -> None:
    # Sulla barra in cui il setup diceva «non ancora», l'evento non e' quello
    # atteso: e' la regola che impedisce di collegarlo a una rilevazione vecchia.
    s = _stock(db)
    row = _setup(db, s, bar=date(2026, 9, 15))
    assert _converti(db, _alert(db, s)) is None
    assert row.status == STATUS_ACTIVE


def test_un_evento_precedente_all_apertura_non_converte(db) -> None:
    s = _stock(db)
    row = _setup(db, s, bar=date(2026, 9, 11))
    assert _converti(db, _alert(db, s), giorno=date(2026, 9, 5)) is None
    assert row.status == STATUS_ACTIVE


def test_la_barra_prevale_sull_orologio_della_scansione(db) -> None:
    # Scansione del 16 che ha letto la barra del 15: l'evento del 16 converte.
    s = _stock(db)
    row = _setup(db, s, bar=date(2026, 9, 15))
    row.first_seen_at = datetime(2026, 9, 16, 7, tzinfo=UTC)
    assert _converti(db, _alert(db, s), giorno=date(2026, 9, 16)) is row


def test_senza_barra_si_ripiega_sul_giorno_di_apertura(db) -> None:
    s = _stock(db)
    row = _setup(db, s, bar=date(2026, 9, 11))
    row.first_seen_bar = None
    assert _converti(db, _alert(db, s), giorno=date(2026, 9, 11)) is None
    assert _converti(db, _alert(db, s), giorno=date(2026, 9, 12)) is row


@pytest.mark.parametrize(("setup_tone", "event_tone", "converte"), [
    ("bull", "bull", True),
    ("bear", "bear", True),
    ("bull", "bear", False),
    ("bear", "bull", False),
    ("undetermined", "bull", True),
    ("undetermined", "bear", True),
    ("bull", None, False),
    ("undetermined", None, False),
])
def test_il_verso_deve_essere_quello_atteso(db, setup_tone, event_tone, converte) -> None:
    s = _stock(db)
    row = _setup(db, s, tone=setup_tone)
    esito = _converti(db, _alert(db, s), tone=event_tone)
    assert (esito is row) is converte
    assert row.status == (STATUS_CONVERTED if converte else STATUS_ACTIVE)


def test_un_altro_detector_non_converte(db) -> None:
    s = _stock(db)
    row = _setup(db, s, detector="sr_flip")
    assert _converti(db, _alert(db, s)) is None
    assert row.status == STATUS_ACTIVE


def test_senza_data_d_evento_non_converte(db) -> None:
    s = _stock(db)
    _setup(db, s)
    assert setup_service.convert_setups_for_event(
        db, _alert(db, s), signal_date=None, tone="bull", price=1.0,
    ) is None


# --- Il ramo della scansione che AGGIORNA l'alert --------------------------

def _df_breakout() -> pd.DataFrame:
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    return pd.DataFrame(rows)


def _rilassa(monkeypatch) -> None:
    base = "app.signals.signal_scan_service.settings."
    monkeypatch.setattr(base + "signal_min_confidence", 0)
    monkeypatch.setattr(base + "signal_require_follow_through", False)
    monkeypatch.setattr(base + "signal_require_trend_alignment", False)
    monkeypatch.setattr(base + "signal_dedup_cooldown_days", 14)
    monkeypatch.setattr(base + "signal_max_age_days", 365)


def test_la_scansione_converte_anche_quando_AGGIORNA_l_alert(db, monkeypatch) -> None:
    _rilassa(monkeypatch)
    s = _stock(db)
    prior = _alert(db, s, giorno=date(2026, 4, 28))
    row = _setup(db, s, bar=date(2026, 4, 29))
    db.commit()

    evaluate_signals(db, s, _df_breakout())   # volume_breakout sul 2026-05-01
    db.commit()

    alerts = db.query(Alert).filter(Alert.stock_id == s.id,
                                    Alert.signal_name == "volume_breakout").all()
    assert [a.id for a in alerts] == [prior.id], "doveva aggiornare, non inserire"
    db.refresh(row)
    assert row.status == STATUS_CONVERTED
    assert row.converted_alert_id == prior.id
    assert row.converted_signal_date == date(2026, 5, 1)
    assert row.converted_price == 110.0


def test_l_evento_resta_fermo_quando_l_alert_si_sposta(db) -> None:
    s = _stock(db)
    row = _setup(db, s, bar=date(2026, 9, 11))
    a = _alert(db, s)
    _converti(db, a)
    # La scansione continua ad aggiornare l'alert finche' la condizione tiene.
    a.signal_date = date(2026, 10, 8)
    a.trigger_price = 70.0
    db.flush()
    db.refresh(row)
    assert row.converted_signal_date == date(2026, 9, 15)
    assert row.converted_price == 50.0


# --- Le statistiche --------------------------------------------------------

def test_i_conteggi_distinguono_chiusi_tasso_ed_esclusi(db) -> None:
    ora = datetime(2026, 9, 1, tzinfo=UTC)
    s = _stock(db)
    _setup(db, s, detector="a", status=STATUS_CONVERTED, resolved_at=ora,
           conversion_source=CONVERSION_LIVE, converted_signal_date=date(2026, 9, 1))
    _setup(db, s, detector="b", status=STATUS_EXPIRED, resolved_at=ora, closed_reason="stale")
    _setup(db, s, detector="c", status=STATUS_EXPIRED, resolved_at=ora)            # senza ragione
    _setup(db, s, detector="d", status=STATUS_EXPIRED, resolved_at=ora,
           closed_reason=REASON_DECAYED)
    _setup(db, s, detector="e", status=STATUS_EXPIRED, resolved_at=ora,
           closed_reason=REASON_MISLINKED)
    _setup(db, s, detector="f")
    db.commit()

    st = setup_service.conversion_stats(db)
    assert st["closed_total"] == 5
    assert st["closed"] == 3                      # il denominatore del tasso
    assert st["excluded_from_rate"] == 2
    assert st["mislinked"] == 1 and st["decayed"] == 1
    assert st["closed_without_reason"] == 1
    assert st["conversion_rate"] == round(1 / 3, 3)
    assert st["total"] == 6


def test_i_non_misurabili_non_sono_in_attesa(db) -> None:
    conv = datetime(2026, 9, 1, 20, tzinfo=UTC)
    s = _stock(db)
    # Riconciliato: nessuna data d'evento, mai misurabile.
    _setup(db, s, detector="r", status=STATUS_CONVERTED, resolved_at=conv,
           conversion_source=CONVERSION_RECONCILED)
    # Storico il cui alert si e' spostato OLTRE la conversione: mai misurabile.
    spostato = _alert(db, s, detector="m", giorno=date(2026, 9, 10))
    _setup(db, s, detector="m", status=STATUS_CONVERTED, resolved_at=conv,
           conversion_source=CONVERSION_LEGACY, converted_alert_id=spostato.id)
    # Storico il cui alert e' fermo prima della conversione: in attesa.
    fermo = _alert(db, s, detector="p", giorno=date(2026, 8, 29))
    _setup(db, s, detector="p", status=STATUS_CONVERTED, resolved_at=conv,
           conversion_source=CONVERSION_LEGACY, converted_alert_id=fermo.id)
    # Registrato dal vivo, orizzonte non trascorso: in attesa.
    _setup(db, s, detector="v", status=STATUS_CONVERTED, resolved_at=conv,
           conversion_source=CONVERSION_LIVE, converted_signal_date=date(2026, 9, 1))
    db.commit()

    st = setup_service.conversion_stats(db)
    assert st["converted"] == 4
    assert st["converted_outcome_unavailable"] == 2
    assert st["converted_pending"] == 2


def test_l_anticipo_sul_mercato_e_separato_dall_attesa(db) -> None:
    s = _stock(db)
    for i, (lead, bar_lead) in enumerate([(3, 1), (9, 5), (12, None)]):
        _setup(db, s, detector=f"x{i}", status=STATUS_CONVERTED,
               resolved_at=datetime(2026, 9, 1, tzinfo=UTC),
               lead_days=lead, bar_lead_days=bar_lead)
    db.commit()
    st = setup_service.conversion_stats(db)
    assert st["median_lead_days"] == 9.0
    assert st["median_bar_lead_days"] == 3.0
    assert st["bar_lead_days_n"] == 2


# --- La maturazione dell'esito dell'evento ---------------------------------

def _barre(db, stock, inizio: date, chiusure: list[float]) -> list[date]:
    giorni = []
    d = inizio
    for c in chiusure:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        db.add(OhlcvDaily(stock_id=stock.id, date=d, open=c, high=c, low=c, close=c,
                          volume=1000))
        giorni.append(d)
        d += timedelta(days=1)
    db.flush()
    return giorni


def test_l_esito_si_misura_dalla_barra_dell_evento_non_dell_alert(db, monkeypatch) -> None:
    monkeypatch.setattr(signal_outcome_service, "_horizon_days", lambda _name: 5)
    s = _stock(db)
    chiusure = [float(x) for x in np.linspace(100, 130, 20)]
    giorni = _barre(db, s, date(2026, 6, 1), chiusure)
    a = _alert(db, s, giorno=giorni[12])          # l'alert si e' spostato avanti
    row = _setup(db, s, bar=giorni[0], status=STATUS_CONVERTED,
                 resolved_at=datetime(2026, 6, 3, tzinfo=UTC),
                 conversion_source=CONVERSION_LIVE, converted_alert_id=a.id,
                 converted_signal_date=giorni[2], converted_tone="bull")
    db.commit()

    assert signal_outcome_service.mature_setup_outcomes(db) == 1
    db.refresh(row)
    assert row.outcome_signal_date == giorni[2]
    assert row.outcome_horizon_days == 5
    assert row.outcome_fwd_return == pytest.approx(chiusure[7] / chiusure[2] - 1.0)
    # Meno di dieci titoli: nessun riferimento dell'universo, ASSENTE non negativo.
    assert row.outcome_mkt_neutral_hit is None
    assert row.outcome_matured_at is not None
    # Idempotente.
    assert signal_outcome_service.mature_setup_outcomes(db) == 0


def test_orizzonte_non_trascorso_resta_in_attesa(db, monkeypatch) -> None:
    monkeypatch.setattr(signal_outcome_service, "_horizon_days", lambda _name: 5)
    s = _stock(db)
    giorni = _barre(db, s, date(2026, 6, 1), [100.0] * 6)
    row = _setup(db, s, bar=giorni[0], status=STATUS_CONVERTED,
                 conversion_source=CONVERSION_LIVE,
                 converted_signal_date=giorni[2], converted_tone="bull")
    db.commit()
    assert signal_outcome_service.mature_setup_outcomes(db) == 0
    assert row.outcome_matured_at is None


def _esito_magazzino(db, alert, giorno: date, hit: int) -> None:
    db.add(SignalOutcome(
        alert_id=alert.id, stock_id=alert.stock_id, detector=alert.signal_name,
        signal_date=giorno, tone="bull", horizon_days=21, entry_close=100.0,
        forward_close=103.0, fwd_return=0.03, universe_mean_fwd=0.0,
        mkt_neutral_excess=0.03, abs_hit=1, mkt_neutral_hit=hit,
    ))
    db.flush()


def test_lo_storico_senza_data_accetta_solo_un_esito_non_successivo(db) -> None:
    conv = datetime(2026, 9, 1, 20, tzinfo=UTC)
    s = _stock(db)
    prima = _alert(db, s, detector="ok", giorno=date(2026, 8, 30))
    _esito_magazzino(db, prima, date(2026, 8, 30), 1)
    buono = _setup(db, s, detector="ok", status=STATUS_CONVERTED, resolved_at=conv,
                   conversion_source=CONVERSION_LEGACY, converted_alert_id=prima.id)
    dopo = _alert(db, s, detector="ko", giorno=date(2026, 9, 5))
    _esito_magazzino(db, dopo, date(2026, 9, 5), 1)
    cattivo = _setup(db, s, detector="ko", status=STATUS_CONVERTED, resolved_at=conv,
                     conversion_source=CONVERSION_LEGACY, converted_alert_id=dopo.id)
    ric = _alert(db, s, detector="ri", giorno=date(2026, 8, 30))
    _esito_magazzino(db, ric, date(2026, 8, 30), 1)
    riconciliato = _setup(db, s, detector="ri", status=STATUS_CONVERTED, resolved_at=conv,
                          conversion_source=CONVERSION_RECONCILED, converted_alert_id=ric.id)
    db.commit()

    assert signal_outcome_service.mature_setup_outcomes(db) == 1
    assert buono.outcome_signal_date == date(2026, 8, 30)
    assert buono.outcome_mkt_neutral_hit == 1
    assert cattivo.outcome_matured_at is None
    assert riconciliato.outcome_matured_at is None

    st = setup_service.conversion_stats(db)
    assert st["converted_positive"] == 1
    assert st["converted_outcome_unavailable"] == 2
    assert st["converted_pending"] == 0


def test_un_attesa_nello_stesso_giorno_vale_zero_giorni(db) -> None:
    # Aperto dalla scansione del mattino, convertito da quella della sera: il
    # preavviso fino alla rilevazione e' ZERO giorni, non uno.
    s = _stock(db)
    row = _setup(db, s, bar=date(2026, 9, 11))
    row.first_seen_at = datetime.now(UTC)
    _converti(db, _alert(db, s))
    assert row.lead_days == 0


def test_un_alert_fermo_sul_giorno_della_conversione_resta_misurabile(db) -> None:
    # Il confine esatto: l'esito misurerebbe una barra NON successiva alla
    # conversione, quindi e' in attesa, non perso.
    conv = datetime(2026, 9, 1, 20, tzinfo=UTC)
    s = _stock(db)
    stesso = _alert(db, s, detector="z", giorno=date(2026, 9, 1))
    _setup(db, s, detector="z", status=STATUS_CONVERTED, resolved_at=conv,
           conversion_source=CONVERSION_LEGACY, converted_alert_id=stesso.id)
    db.commit()
    st = setup_service.conversion_stats(db)
    assert st["converted_outcome_unavailable"] == 0
    assert st["converted_pending"] == 1
