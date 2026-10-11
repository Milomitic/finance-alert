"""L'archivio dei consensi macro (2026-10-11).

Forexfactory pubblica solo la settimana in corso: senza archivio, l'ultimo dato
non si puo' confrontare con la SUA stima, e lo storico non ha previsti."""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.macro import MacroConsenso
from app.services import calendar_service as cal
from app.services import forexfactory_consensus as ff
from app.services import macro_consenso_service as arch

ADESSO = datetime(2026, 10, 11, 12, tzinfo=UTC)


def _ff(title: str, giorno: date, forecast: str, actual: str = "", previous: str = "", country: str = "USD"):
    return ff.FFEvent(title=title, country=country, date=giorno, impact="High",
                      forecast=forecast, previous=previous, actual=actual)


@pytest.fixture
def settimana(monkeypatch):
    eventi: list = []
    monkeypatch.setattr(ff, "_get_events", lambda: eventi)
    return eventi


def test_archivia_e_conserva_il_dato_uscito(db: Session, settimana) -> None:
    settimana.append(_ff("CPI m/m", date(2026, 10, 14), "0.6%", previous="0.4%"))
    settimana.append(_ff("Non-Farm Employment Change", date(2026, 10, 2), "150K", "212K", "130K"))
    assert arch.archivia(db, adesso=ADESSO) == 2
    cpi = db.query(MacroConsenso).filter_by(etichetta="US CPI release").one()
    assert (cpi.previsto, cpi.attuale, cpi.precedente, cpi.formato) == (0.6, None, 0.4, "%")
    nfp = db.query(MacroConsenso).filter_by(etichetta="US NFP / Non-Farm Payrolls").one()
    # Nella scala in cui e' scritto: «212K» e' 212.
    assert (nfp.previsto, nfp.attuale, nfp.formato) == (150.0, 212.0, "K")

    # Uscito il dato, il feed lo porta; la settimana dopo non c'e' piu', e la
    # riga resta com'era invece di tornare vuota.
    settimana[0] = _ff("CPI m/m", date(2026, 10, 14), "0.6%", "0.7%", "0.4%")
    arch.archivia(db, adesso=ADESSO)
    settimana.clear()
    settimana.append(_ff("CPI m/m", date(2026, 10, 14), "", "", ""))
    arch.archivia(db, adesso=ADESSO)
    cpi = db.query(MacroConsenso).filter_by(etichetta="US CPI release").one()
    assert (cpi.previsto, cpi.attuale) == (0.6, 0.7)


def test_un_periodo_prende_il_rilascio_che_lo_ha_pubblicato(db: Session) -> None:
    for giorno, previsto in [(date(2026, 9, 11), 0.3), (date(2026, 10, 14), 0.6)]:
        db.add(MacroConsenso(etichetta="US CPI release", data=giorno, titolo="CPI m/m",
                             previsto=previsto, formato="%", aggiornato_il=ADESSO))
    db.commit()
    periodi = [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
    m = arch.per_periodo(db, "US CPI release", periodi)
    # Il rilascio dell'11 settembre e' AGOSTO, quello del 14 ottobre SETTEMBRE.
    assert m[date(2026, 8, 1)].previsto == 0.3
    assert m[date(2026, 9, 1)].previsto == 0.6
    assert date(2026, 7, 1) not in m
    assert arch.ultimo_prima(db, "US CPI release", date(2026, 10, 14)).data == date(2026, 9, 11)


def test_il_rilascio_di_un_mese_che_fred_non_ha_ancora_non_cade_sul_mese_prima(db: Session) -> None:
    """Il caso reale di oggi: FRED arriva ad agosto, il rilascio del 14 ottobre
    pubblica settembre. Senza prolungare la cadenza finirebbe su agosto."""
    db.add(MacroConsenso(etichetta="US CPI release", data=date(2026, 10, 14), titolo="CPI m/m",
                         previsto=0.6, formato="%", aggiornato_il=ADESSO))
    db.commit()
    m = arch.per_periodo(db, "US CPI release", [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)])
    assert m == {}


def _cpi(**k) -> cal.MacroEventDC:
    ev = cal.MacroEventDC(date=date(2026, 10, 14), kind="macro", label="US CPI release", importance="high",
                          region="US", unit="index",
                          history=[(date(2026, 6, 1), 331.5), (date(2026, 7, 1), 332.813), (date(2026, 8, 1), 334.131)])
    for c, v in k.items():
        setattr(ev, c, v)
    return ev


def test_attuale_si_confronta_con_la_stima_del_SUO_rilascio(db: Session) -> None:
    """Prima dell'uscita «Attuale» e' il rilascio di settembre (0.4): la sua
    stima e' quella di settembre, non lo 0.6 previsto per ottobre."""
    db.add(MacroConsenso(etichetta="US CPI release", data=date(2026, 9, 11), titolo="CPI m/m",
                         previsto=0.3, attuale=0.4, formato="%", aggiornato_il=ADESSO))
    db.commit()
    ev = _cpi(attuale_consenso=0.4, previsto_consenso=0.6, precedente_consenso=0.07)
    cal._consenso_dall_archivio(db, ev, "CPI m/m", uscito=False)
    assert ev.previsto_attuale == 0.3


def test_un_rilascio_archiviato_che_non_e_quello_mostrato_non_colora(db: Session) -> None:
    db.add(MacroConsenso(etichetta="US CPI release", data=date(2026, 9, 11), titolo="CPI m/m",
                         previsto=0.3, attuale=0.9, formato="%", aggiornato_il=ADESSO))
    db.commit()
    ev = _cpi(attuale_consenso=0.4, previsto_consenso=0.6)
    cal._consenso_dall_archivio(db, ev, "CPI m/m", uscito=False)
    assert ev.previsto_attuale is None


def test_uscito_il_dato_la_stima_e_quella_del_rilascio_stesso(db: Session) -> None:
    ev = _cpi(attuale_consenso=0.7, previsto_consenso=0.6)
    cal._consenso_dall_archivio(db, ev, "CPI m/m", uscito=True)
    assert ev.previsto_attuale == 0.6


def test_lo_storico_porta_previsto_e_attuale_nell_unita_del_consenso(db: Session) -> None:
    db.add(MacroConsenso(etichetta="US CPI release", data=date(2026, 9, 11), titolo="CPI m/m",
                         previsto=0.3, attuale=0.4, formato="%", aggiornato_il=ADESSO))
    db.commit()
    ev = _cpi(attuale_consenso=0.4, previsto_consenso=0.6)
    cal._consenso_dall_archivio(db, ev, "CPI m/m", uscito=False)
    giugno, luglio, agosto = ev.storico_consenso
    assert giugno == (date(2026, 6, 1), None, None)          # nessun mese prima: niente variazione
    assert luglio[1] is None                                 # nessun previsto archiviato
    assert luglio[2] == pytest.approx((332.813 / 331.5 - 1) * 100)   # dai livelli: stessa misura
    assert agosto == (date(2026, 8, 1), 0.3, 0.4)            # dall'archivio, ufficiale


def test_una_serie_che_non_e_la_stessa_misura_non_inventa_lo_storico(db: Session) -> None:
    """Il PPI: FRED +0,96% contro 0,4 pubblicato. Le variazioni dai livelli
    sarebbero di un'altra misura."""
    ev = cal.MacroEventDC(date=date(2026, 10, 15), kind="macro", label="US PPI release", importance="high",
                          region="US", unit="index", attuale_consenso=0.4,
                          history=[(date(2026, 7, 1), 285.181), (date(2026, 8, 1), 287.928)])
    cal._consenso_dall_archivio(db, ev, "PPI m/m", uscito=False)
    assert [a for _, _, a in ev.storico_consenso] == [None, None]


def test_il_job(db: Session, settimana, monkeypatch) -> None:
    from app.core import db as db_module
    from app.scheduler.jobs.archivia_consenso_macro import run_archivia_consenso_macro

    monkeypatch.setattr(db_module, "SessionLocal", lambda: db)
    settimana.append(_ff("CPI m/m", date(2026, 10, 14), "0.6%", previous="0.4%"))
    run_archivia_consenso_macro()
    assert db.query(MacroConsenso).count() == 1


def test_il_job_non_cade_se_il_feed_e_giu(db: Session, monkeypatch) -> None:
    from app.core import db as db_module
    from app.scheduler.jobs.archivia_consenso_macro import run_archivia_consenso_macro

    monkeypatch.setattr(db_module, "SessionLocal", lambda: db)

    def giu():
        raise OSError("rete")

    monkeypatch.setattr(ff, "_get_events", giu)
    run_archivia_consenso_macro()
    assert db.query(MacroConsenso).count() == 0


def test_due_titoli_dello_stesso_rilascio_non_fanno_cadere_il_giro(db: Session, settimana) -> None:
    """2026-10-11 in produzione: «Core Retail Sales m/m» e «Retail Sales m/m»
    lo stesso giorno, e la regola li prendeva entrambi. Ora un rilascio, un
    evento, e per le vendite il COMPLESSIVO — la misura della serie FRED."""
    settimana.append(_ff("Core Retail Sales m/m", date(2026, 10, 15), "0.5%", previous="1.4%"))
    settimana.append(_ff("Retail Sales m/m", date(2026, 10, 15), "0.3%", previous="1.2%"))
    settimana.append(_ff("Advance GDP Price Index q/q", date(2026, 10, 29), "2.1%", previous="2.0%"))
    settimana.append(_ff("Advance GDP q/q", date(2026, 10, 29), "1.8%", previous="3.0%"))
    # Due titoli che la regola stretta prende ENTRAMBI, lo stesso giorno: e' il
    # caso che solo la deduplica copre.
    settimana.append(_ff("GDP q/q", date(2026, 10, 29), "9.9%", previous="9.9%"))
    arch.archivia(db, adesso=ADESSO)
    vendite = db.query(MacroConsenso).filter_by(etichetta="US Retail Sales").one()
    assert (vendite.titolo, vendite.previsto) == ("Retail Sales m/m", 0.3)
    pil = db.query(MacroConsenso).filter_by(etichetta="US GDP (real)").one()
    assert (pil.titolo, pil.previsto) == ("Advance GDP q/q", 1.8)
