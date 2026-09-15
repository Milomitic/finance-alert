"""Gli alert rimasti sulla base prezzo vecchia (FA-069).

Una riparazione riscrive la SERIE e lascia `alerts.trigger_price` dov'era. In
produzione, 2026-09-15: 39 alert su 8 titoli, 11 visibili, e piu' della meta'
lasciati dal rebase AUTOMATICO del fetch, non dallo script di riparazione.

Casi presi dalla misura, non inventati: APH a x2.000 esatto, MRNA che a x2.29
contro la propria barra di segnale E' sulla base giusta (rilevazione tardiva
dopo un movimento vero), un titolo di Hong Kong datato avanti rispetto a UTC.
"""

from datetime import UTC, date, datetime, time, timedelta

import pandas as pd
import pytest
from loguru import logger

from app.models import Alert, OhlcvDaily, Stock
from app.scripts import repair_price_basis
from app.services import ohlcv_service
from app.services.ohlcv_service import (
    _BASIS_RATIO_HIGH,
    _BASIS_RATIO_LOW,
    find_alerts_off_basis,
)

D0 = date(2026, 7, 6)


def _stock(db, ticker: str = "APH") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.commit()
    return s


def _barre(db, stock: Stock, chiusure: dict[date, float]) -> None:
    for d, c in chiusure.items():
        db.add(OhlcvDaily(
            stock_id=stock.id, date=d, open=c, high=c, low=c, close=c, volume=1_000,
        ))
    db.commit()


def _alert(
    db, stock: Stock, signal_date: date | None, *, trigger: float,
    triggered_at: datetime | None = None, archiviato: bool = False,
) -> Alert:
    a = Alert(
        stock_id=stock.id,
        signal_name="trend_pullback",
        signal_date=signal_date,
        # Di default il giorno dopo il segnale, come uno scan notturno.
        triggered_at=triggered_at or datetime.combine(
            (signal_date or D0) + timedelta(days=1), time(10), tzinfo=UTC,
        ),
        trigger_price=trigger,
        snapshot="{}",
        archived_at=datetime(2026, 9, 1, tzinfo=UTC) if archiviato else None,
    )
    db.add(a)
    db.commit()
    return a


def test_un_rebase_2_a_1_lascia_l_alert_al_doppio(db):
    s = _stock(db, "APH")
    _barre(db, s, {D0: 83.405, D0 + timedelta(days=1): 85.665})
    a = _alert(db, s, D0, trigger=171.33)

    check = find_alerts_off_basis(db)

    [o] = check.off
    assert (o.alert_id, o.ticker, o.signal_date, o.visible) == (a.id, "APH", D0, True)
    # La chiusura PIU' VICINA mostra il fattore vero: contro la barra del segnale
    # il rapporto sarebbe x2.054, contro quella su cui l'alert e' stato prezzato
    # e' x2.000 — la stessa forma di APH 17477 in produzione.
    assert o.nearest_close == pytest.approx(85.665)
    assert o.ratio == pytest.approx(2.0)
    assert check.compared == 1


def test_un_alert_sulla_base_giusta_non_compare(db):
    s = _stock(db)
    _barre(db, s, {D0: 83.405})
    _alert(db, s, D0, trigger=83.405)

    check = find_alerts_off_basis(db)

    assert check.off == []
    # Il pavimento: una lista vuota perche' non si e' confrontato niente sarebbe
    # vera di niente.
    assert check.compared == 1


def test_una_rilevazione_tardiva_dopo_un_movimento_vero_non_e_fuori_base(db):
    s = _stock(db, "MRNA")
    _barre(db, s, {D0: 63.32, D0 + timedelta(days=7): 145.13})
    _alert(
        db, s, D0, trigger=145.13,
        triggered_at=datetime.combine(D0 + timedelta(days=10), time(9), tzinfo=UTC),
    )

    check = find_alerts_off_basis(db)

    assert (check.compared, check.off) == (1, [])
    # Controllo negativo: il confronto con la sola barra del segnale — la prima
    # idea, e la misura di partenza della voce — lo segnalerebbe.
    assert not _BASIS_RATIO_LOW <= 145.13 / 63.32 <= _BASIS_RATIO_HIGH


@pytest.mark.parametrize(
    "fattore",
    [
        _BASIS_RATIO_HIGH * 0.999,
        _BASIS_RATIO_HIGH * 1.001,
        _BASIS_RATIO_LOW * 1.001,
        _BASIS_RATIO_LOW * 0.999,
    ],
)
def test_la_banda_e_quella_dell_ingest(db, fattore):
    """Il rapporto e l'ingest non possono dissentire su cosa sia un cambio di base.

    La stessa coppia di prezzi, letta dai due: `_check_price_basis` con il
    vecchio prezzo memorizzato e il nuovo in arrivo, il rapporto con il trigger
    e la chiusura attuale."""
    s = _stock(db, "ALRT")
    _barre(db, s, {D0: 100.0})
    _alert(db, s, D0, trigger=100.0 * fattore)
    fuori = bool(find_alerts_off_basis(db, [s.id]).off)

    t = _stock(db, "INGS")
    _barre(db, t, {D0: 100.0 * fattore})
    try:
        ohlcv_service._check_price_basis(db, t, [{"date": D0, "close": 100.0}])
        cambio_dichiarato = False
    except ohlcv_service.PriceBasisMismatch:
        cambio_dichiarato = True

    assert fuori == cambio_dichiarato
    # E non per caso: i quattro fattori coprono entrambi gli esiti.
    assert fuori == (fattore > _BASIS_RATIO_HIGH or fattore < _BASIS_RATIO_LOW)


def test_la_finestra_ha_un_giorno_di_margine_e_non_di_piu(db):
    sera_utc = datetime.combine(D0, time(23), tzinfo=UTC)

    # La barra di Hong Kong datata il giorno dopo la data UTC dello scan.
    hk = _stock(db, "0700.HK")
    _barre(db, hk, {D0: 50.0, D0 + timedelta(days=1): 100.0})
    _alert(db, hk, D0, trigger=100.0, triggered_at=sera_utc)

    oltre = _stock(db, "0005.HK")
    _barre(db, oltre, {D0: 50.0, D0 + timedelta(days=2): 100.0})
    _alert(db, oltre, D0, trigger=100.0, triggered_at=sera_utc)

    assert [o.ticker for o in find_alerts_off_basis(db).off] == ["0005.HK"]


def test_senza_barre_nella_finestra_non_si_indovina(db):
    s = _stock(db, "SOXS")
    # Troncato: restano solo barre posteriori alla finestra dell'alert.
    _barre(db, s, {D0 + timedelta(days=30): 60.0})
    _alert(db, s, D0, trigger=1159.5)
    # Un alert legacy senza signal_date non ha una finestra: non si conta.
    _alert(db, s, None, trigger=1159.5)

    check = find_alerts_off_basis(db)

    assert (check.compared, check.not_comparable, check.off) == (0, 1, [])


def test_un_alert_archiviato_si_controlla_lo_stesso(db):
    s = _stock(db, "KLAC")
    _barre(db, s, {D0: 150.0})
    _alert(db, s, D0, trigger=1500.0, archiviato=True)

    [o] = find_alerts_off_basis(db).off

    assert o.visible is False
    assert o.ratio == pytest.approx(10.0)


def test_il_perimetro_per_titolo(db):
    aph, mnst = _stock(db, "APH"), _stock(db, "MNST")
    for s in (aph, mnst):
        _barre(db, s, {D0: 50.0})
        _alert(db, s, D0, trigger=100.0)

    solo = find_alerts_off_basis(db, [mnst.id])

    assert [o.ticker for o in solo.off] == ["MNST"]
    assert solo.compared == 1
    assert len(find_alerts_off_basis(db).off) == 2


# ---------------------------------------------------------------------------
# Il rebase automatico, che ha prodotto piu' di meta' del residuo
# ---------------------------------------------------------------------------

def _frame(start: date, chiusure: list[float]) -> pd.DataFrame:
    idx = pd.to_datetime([start + timedelta(days=i) for i in range(len(chiusure))])
    return pd.DataFrame(
        {
            "Open": chiusure, "High": [c + 1 for c in chiusure],
            "Low": [c - 1 for c in chiusure], "Close": chiusure,
            "Volume": [1_000] * len(chiusure),
        },
        index=idx,
    )


def _rebase_con_split(db, monkeypatch, *, con_alert: bool) -> list[str]:
    d0 = date(2026, 6, 1)
    s = _stock(db, "SPLT")
    _barre(db, s, {d0 + timedelta(days=i): c for i, c in enumerate([400.0, 402.0, 404.0])})
    if con_alert:
        _alert(db, s, d0 + timedelta(days=1), trigger=402.0)

    sovrapposta = d0 + timedelta(days=2)
    incrementale = _frame(sovrapposta, [40.4, 41.0])
    completa = _frame(d0, [40.0, 40.2, 40.4, 41.0])
    chiamate: list[dict] = []

    def download_finto(tickers, **kw):
        chiamate.append(kw)
        frame = incrementale if len(chiamate) == 1 else completa
        return pd.concat({"SPLT": frame}, axis=1)

    monkeypatch.setattr(ohlcv_service, "_yf_download", download_finto)
    righe: list[str] = []
    sink = logger.add(lambda m: righe.append(str(m)), level="WARNING")
    try:
        res = ohlcv_service.fetch_and_upsert(db, [s], start=sovrapposta)
        db.commit()
    finally:
        logger.remove(sink)
    assert res.stocks_rebased == 1
    return [r for r in righe if "FA-069" in r]


def test_il_rebase_automatico_dice_quanti_alert_lascia_indietro(db, monkeypatch):
    [riga] = _rebase_con_split(db, monkeypatch, con_alert=True)
    assert "SPLT" in riga
    assert "1 alert" in riga


def test_un_rebase_senza_alert_non_avverte_di_niente(db, monkeypatch):
    assert _rebase_con_split(db, monkeypatch, con_alert=False) == []


def test_il_rapporto_esce_anche_quando_la_serie_non_ha_rotture(db, monkeypatch, capsys):
    """⚠️ Il caso reale, non quello limite: dopo una riparazione la serie e'
    pulita, quindi lo script trova «nessuna discontinuita'» ed esce. Il residuo
    esiste esattamente li'."""
    s = _stock(db, "APH")
    _barre(db, s, {D0: 83.405})
    _alert(db, s, D0, trigger=166.81)
    monkeypatch.setattr(repair_price_basis, "SessionLocal", lambda: db)
    monkeypatch.setattr("sys.argv", ["repair_price_basis", "--no-source-check"])

    repair_price_basis.main()

    out = capsys.readouterr().out
    assert "nessuna discontinuita'" in out
    assert "alert sulla base prezzo vecchia: 1 su 1 confrontabili (1 visibili)" in out
    assert "x2.000" in out
