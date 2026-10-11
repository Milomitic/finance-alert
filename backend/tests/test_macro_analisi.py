"""I numeri della pagina di dettaglio macro (2026-10-11)."""
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.models.macro import MacroObservation, MacroReleaseDate, MacroSeries
from app.services import macro_analisi_service as an


def _mesi(dal: date, n: int) -> list[date]:
    out, d = [], dal
    for _ in range(n):
        out.append(d)
        d = (d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1))
    return out


def _serie(db: Session, unit: str, punti: list[tuple[date, float]], codice: str = "X") -> MacroSeries:
    s = MacroSeries(fred_series_id=codice, label=f"Prova {codice}", region="US", importance="high", unit=unit)
    db.add(s)
    db.flush()
    for d, v in punti:
        db.add(MacroObservation(series_id=s.id, date=d, value=v))
    db.commit()
    return s


def test_su_un_indice_le_variazioni_sono_in_percento_mese_e_anno() -> None:
    mesi = _mesi(date(2024, 1, 1), 14)
    oss = [(d, 100.0 * 1.01 ** i) for i, d in enumerate(mesi)]
    v = an.variazioni(oss, tasso=False)
    assert v[0].sul_periodo is None and v[0].sull_anno is None
    assert v[1].sul_periodo == pytest.approx(1.0)
    # Dodici mesi dopo: (1,01^12 - 1) * 100.
    assert v[12].sull_anno == pytest.approx((1.01 ** 12 - 1) * 100)


def test_su_un_tasso_sono_punti_e_le_ripetizioni_non_contano() -> None:
    """3,75 -> 4,00 e' +0,25 pp, non +6,7%; trenta giorni uguali non sono
    trenta variazioni."""
    giorni = [date(2026, 1, 1) + timedelta(days=i) for i in range(40)]
    oss = [(d, 3.75 if i < 20 else 4.0) for i, d in enumerate(giorni)]
    v = an.variazioni(oss, tasso=True)
    assert [x.valore for x in v] == [3.75, 4.0]
    assert v[1].sul_periodo == pytest.approx(0.25)


def test_le_statistiche_dicono_quanto_e_insolita_l_ultima(db: Session) -> None:
    mesi = _mesi(date(2023, 1, 1), 30)
    valori, x = [], 100.0
    for i in range(30):
        x *= 1.003 if i < 29 else 1.012  # l'ultimo mese quattro volte il solito
        valori.append(x)
    s = _serie(db, "index", list(zip(mesi, valori, strict=True)))
    a = an.analisi(db, s, oggi=date(2026, 1, 1))
    assert a.unita_variazione == "%"
    assert a.ultima == pytest.approx(1.2)
    assert a.zscore > 3
    assert a.percentile == pytest.approx(100.0)
    assert a.serie == 29                       # tutti rialzi
    assert a.massimo == (mesi[-1], valori[-1])
    assert a.annualizzata_3m == pytest.approx(((valori[-1] / valori[-4]) ** 4 - 1) * 100)


def test_con_poche_variazioni_lo_zscore_non_si_calcola(db: Session) -> None:
    mesi = _mesi(date(2026, 1, 1), 5)
    s = _serie(db, "index", [(d, 100.0 + i) for i, d in enumerate(mesi)])
    a = an.analisi(db, s, oggi=date(2026, 7, 1))
    assert a.ultima is not None
    assert (a.zscore, a.percentile, a.media) == (None, None, None)


def _spy(db: Session, chiusure: dict[date, float]) -> None:
    spy = Stock(ticker="SPY", exchange="NYSE Arca", name="SPDR S&P 500")
    db.add(spy)
    db.flush()
    for d, c in chiusure.items():
        db.add(OhlcvDaily(stock_id=spy.id, date=d, open=c, high=c, low=c, close=c, volume=1))
    db.commit()


def test_la_reazione_dello_spy_nei_giorni_di_rilascio(db: Session) -> None:
    """Sei rilasci con un movimento del 2%, gli altri giorni dello 0,5%."""
    inizio = date(2026, 1, 5)
    giorni = [inizio + timedelta(days=i) for i in range(60)]
    rilasci = giorni[5::9][:6]
    chiusure, c = {}, 100.0
    for d in giorni:
        c *= 1.02 if d in rilasci else (1.005 if d.day % 2 else 0.995)
        chiusure[d] = c
    _spy(db, chiusure)
    s = _serie(db, "index", [(d, 100.0) for d in _mesi(date(2025, 1, 1), 3)], codice="R")
    for d in rilasci:
        db.add(MacroReleaseDate(series_id=s.id, date=d))
    db.commit()
    a = an.analisi(db, s, oggi=date(2026, 6, 1))
    assert a.reazione.n == 6
    assert a.reazione.medio_rilascio == pytest.approx(2.0, abs=1e-6)
    assert a.reazione.medio_altri == pytest.approx(0.5, abs=0.01)


def test_pochi_rilasci_non_danno_una_reazione(db: Session) -> None:
    s = _serie(db, "index", [(date(2026, 1, 1), 1.0)], codice="P")
    db.add(MacroReleaseDate(series_id=s.id, date=date(2026, 2, 1)))
    db.commit()
    assert an.analisi(db, s, oggi=date(2026, 6, 1)).reazione is None


def test_la_correlazione_col_mese_dello_spy(db: Session) -> None:
    """La serie sale quando lo SPY sale nello stesso mese: r vicino a 1."""
    mesi = _mesi(date(2024, 1, 1), 24)
    serie, spy, v, c = [], {}, 100.0, 400.0
    for i, d in enumerate(mesi):
        cambio = (i % 5 - 2) * 0.2      # varia in segno e ampiezza
        v *= 1 + cambio / 100
        c *= 1 + cambio * 3 / 100
        serie.append((d, v))
        spy[d + timedelta(days=20)] = c  # una chiusura dentro il mese
    _spy(db, spy)
    s = _serie(db, "index", serie, codice="C")
    a = an.analisi(db, s, oggi=date(2026, 6, 1))
    assert a.correlazione is not None
    assert a.correlazione.r == pytest.approx(1.0, abs=0.01)
    assert a.correlazione.n >= an.MIN_MESI_CORRELAZIONE


def test_una_serie_non_mensile_non_ha_correlazione_mensile(db: Session) -> None:
    giorni = [date(2026, 1, 1) + timedelta(days=i) for i in range(60)]
    s = _serie(db, "pct", [(d, 3.0 + (i // 10) * 0.25) for i, d in enumerate(giorni)], codice="D")
    a = an.analisi(db, s, oggi=date(2026, 6, 1))
    assert a.unita_variazione == "pp"
    assert a.correlazione is None
