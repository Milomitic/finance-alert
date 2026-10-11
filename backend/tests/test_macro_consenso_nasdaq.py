"""I consensi dei rilasci PASSATI, dal calendario di Nasdaq (2026-10-11).

Forexfactory pubblica solo la settimana in corso; Nasdaq risponde per
qualunque giorno. Il punto delicato e' che il CPI compare due volte col nome
«CPI», sul mese e sull'anno, e nessun campo dice quale sia quale."""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.macro import MacroConsenso, MacroObservation, MacroSeries
from app.scheduler.jobs import archivia_consenso_macro as job
from app.scripts import backfill_consenso_macro as bf
from app.services import macro_consenso_service as arch
from app.services import nasdaq_consensus as nq

ADESSO = datetime(2026, 10, 11, 12, tzinfo=UTC)


def _ev(nome: str, actual: str | None, consensus: str | None, previous: str | None = None,
        paese: str = "United States") -> nq.NasdaqEvento:
    return nq.NasdaqEvento(paese=paese, nome=nome, actual=actual, consensus=consensus, previous=previous)


# ── la lettura della fonte ────────────────────────────────────────────────


class _Risposta:
    def __init__(self, corpo):
        self.corpo = corpo

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self.corpo


class _Sessione:
    def __init__(self, corpo):
        self.corpo, self.chiamate = corpo, []

    def get(self, url, **kw):
        self.chiamate.append((url, kw))
        return _Risposta(self.corpo)


def test_legge_un_giorno_e_svuota_i_campi_vuoti() -> None:
    s = _Sessione({"data": {"rows": [
        {"country": "United States", "eventName": "CPI", "actual": "0.4%", "consensus": "0.4%", "previous": "0.1%"},
        {"country": "Japan", "eventName": "BoJ Monetary Policy Statement", "actual": "&nbsp;",
         "consensus": " ", "previous": "&nbsp;"},
    ]}})
    eventi = nq.eventi_del_giorno(date(2026, 9, 12), sessione=s)
    assert eventi[0] == _ev("CPI", "0.4%", "0.4%", "0.1%")
    assert (eventi[1].actual, eventi[1].consensus, eventi[1].previous) == (None, None, None)
    _url, kw = s.chiamate[0]
    # La fonte data al giorno dopo: il CPI uscito il 12 si chiede col 13. Senza,
    # le uscite del venerdi' stanno al sabato e un riempimento sui feriali le perde.
    assert kw["params"] == {"date": "2026-09-13"}
    # Senza un User-Agent da browser l'API non risponde.
    assert "Mozilla" in kw["headers"]["User-Agent"]


def test_un_giorno_senza_righe_e_vuoto() -> None:
    assert nq.eventi_del_giorno(date(2026, 9, 13), sessione=_Sessione({"data": None})) == []


# ── quale riga e' sul mese e quale sull'anno ──────────────────────────────

MESE, ANNO = _ev("CPI", "0.4%", "0.4%", "0.1%"), _ev("CPI", "3.4%", "3.4%", "3.4%")


@pytest.mark.parametrize("righe", [[MESE, ANNO], [ANNO, MESE]])
def test_le_due_righe_si_riconoscono_in_qualunque_ordine(righe) -> None:
    # Il PPI di settembre arrivava con la riga annua PRIMA: l'ordine non dice niente.
    assert nq.assegna(righe, "periodo", (0.39, 3.35)) == (MESE, ANNO)
    assert nq.assegna(righe, "periodo") == (MESE, ANNO)


def test_in_un_mese_di_deflazione_decide_fred() -> None:
    # Aprile 2020: sul mese −0,8, sull'anno +0,3. La riga piu' piccola in valore
    # assoluto e' quella ANNUA, e solo il confronto con FRED lo sa.
    mese, anno = _ev("CPI", "-0.8%", "-0.7%"), _ev("CPI", "0.3%", "0.4%")
    assert nq.assegna([anno, mese], "periodo") == (anno, mese)  # il ripiego sbaglia
    assert nq.assegna([anno, mese], "periodo", (-0.76, 0.33)) == (mese, anno)
    assert nq.assegna([anno, mese], "periodo", (-0.76, None)) == (mese, anno)
    assert nq.assegna([anno, mese], "periodo", (None, 0.33)) == (mese, anno)


def test_una_riga_sola_e_la_misura_principale() -> None:
    # Il PIL ha una riga, annualizzata (2,2%): somiglia piu' alla variazione
    # ANNUA di FRED (2,0) che a quella trimestrale (0,5), e sceglierla per
    # somiglianza la metterebbe nella colonna sbagliata.
    pil = _ev("GDP", "2.2%", "1.5%", "2.1%")
    assert nq.assegna([pil], "periodo", (0.5, 2.0)) == (pil, None)
    assert nq.assegna([], "periodo") == (None, None)


def test_un_livello_e_una_misura_annua() -> None:
    tasso = _ev("Unemployment Rate", "4.2%", "4.1%")
    assert nq.assegna([tasso], "livello") == (tasso, None)
    assert nq.assegna([MESE, ANNO], "anno") == (ANNO, None)
    # Una riga senza nessun valore non si confronta: l'altra e' la sola nota.
    vuota = _ev("CPI", None, None)
    assert nq.assegna([vuota, ANNO], "periodo") == (ANNO, None)
    assert nq.assegna([ANNO, vuota], "anno") == (ANNO, None)


# ── l'archivio ────────────────────────────────────────────────────────────


def _giorni(per_giorno: dict[date, list[nq.NasdaqEvento]]):
    def leggi(g: date):
        if g not in per_giorno:
            raise RuntimeError("503")
        return per_giorno[g]
    return leggi


def _cpi_fred(db: Session) -> None:
    s = MacroSeries(fred_series_id="CPIAUCSL", label="US CPI release", region="US", importance="high", unit="index")
    db.add(s)
    db.flush()
    for i in range(14):
        db.add(MacroObservation(series_id=s.id, date=date(2025 + (7 + i) // 12, (7 + i) % 12 + 1, 1),
                                value=100 * 1.004 ** i))
    db.commit()


def test_archivia_i_rilasci_passati_con_la_stima_sull_anno(db: Session) -> None:
    _cpi_fred(db)
    giorno = date(2026, 9, 12)
    n, mancanti = arch.archivia_nasdaq(db, [giorno, date(2026, 9, 14)], adesso=ADESSO, leggi=_giorni({giorno: [
        ANNO, MESE,
        _ev("Core CPI", "0.3%", "0.2%"),
        _ev("Nonfarm Payrolls", "29K", "89K", "133K"),
        _ev("CPI", "3.8%", "3.7%", paese="Euro Zone"),
        _ev("Atlanta Fed GDPNow", "4.4%", "4.7%"),
    ]}))
    assert (n, mancanti) == (3, [date(2026, 9, 14)])
    cpi = db.query(MacroConsenso).filter_by(etichetta="US CPI release").one()
    assert (cpi.previsto, cpi.attuale, cpi.precedente, cpi.formato) == (0.4, 0.4, 0.1, "%")
    assert (cpi.previsto_annuo, cpi.attuale_annuo) == (3.4, 3.4)
    assert cpi.titolo == "Nasdaq · CPI"
    nfp = db.query(MacroConsenso).filter_by(etichetta="US NFP / Non-Farm Payrolls").one()
    # Nella scala in cui e' scritto, come Forexfactory: «29K» e' 29.
    assert (nfp.previsto, nfp.attuale, nfp.formato) == (89.0, 29.0, "K")
    hicp = db.query(MacroConsenso).filter_by(etichetta="Eurozone HICP flash").one()
    assert (hicp.previsto, hicp.previsto_annuo) == (3.7, None)


def test_non_tocca_cio_che_forexfactory_ha_gia_archiviato(db: Session) -> None:
    # Forexfactory data al 13 un rilascio che Nasdaq data al 12: e' lo stesso.
    db.add(MacroConsenso(etichetta="US CPI release", data=date(2026, 9, 13), titolo="CPI m/m",
                         previsto=0.3, formato="%", aggiornato_il=ADESSO))
    db.commit()
    giorno = date(2026, 9, 12)
    arch.archivia_nasdaq(db, [giorno], adesso=ADESSO, leggi=_giorni({giorno: [MESE, ANNO]}))
    righe = db.query(MacroConsenso).filter_by(etichetta="US CPI release").all()
    assert len(righe) == 1
    r = righe[0]
    # Il previsto resta quello di Forexfactory; Nasdaq aggiunge cio' che manca.
    assert (r.data, r.previsto, r.attuale, r.titolo) == (date(2026, 9, 13), 0.3, 0.4, "CPI m/m")
    assert (r.previsto_annuo, r.attuale_annuo) == (3.4, 3.4)

    # Un giro successivo senza il dato annuo non lo cancella.
    arch.archivia_nasdaq(db, [giorno], adesso=ADESSO,
                         leggi=_giorni({giorno: [MESE, _ev("CPI", None, None)]}))
    db.refresh(r)
    assert (r.previsto_annuo, r.attuale_annuo) == (3.4, 3.4)


def test_un_evento_senza_valori_non_crea_righe(db: Session) -> None:
    giorno = date(2026, 9, 18)
    n, _ = arch.archivia_nasdaq(db, [giorno], adesso=ADESSO,
                                leggi=_giorni({giorno: [_ev("BoJ Interest Rate Decision", None, None, paese="Japan")]}))
    assert n == 0
    assert db.query(MacroConsenso).count() == 0


# ── l'esito: il colore e' contro la stima, non il segno ───────────────────


def test_esito_contro_la_stima_non_contro_lo_zero() -> None:
    assert arch.esito(0.2, 0.4) == "sotto"
    assert arch.esito(-0.1, -0.3) == "sopra"
    assert arch.esito(0.4, 0.4) == "in_linea"
    # Due float dalla stessa stringa con un'aritmetica di mezzo: ancora in linea.
    assert arch.esito(0.1 + 0.2, 0.3) == "in_linea"
    assert arch.esito(None, 0.4) is None
    assert arch.esito(0.4, None) is None


def test_ogni_variazione_si_confronta_con_la_sua_misura() -> None:
    r = MacroConsenso(etichetta="US CPI release", data=date(2026, 9, 12), titolo="CPI", previsto=0.4,
                      attuale=0.5, previsto_annuo=3.4, attuale_annuo=3.3, formato="%")
    assert arch.esiti(r, "periodo") == ("sopra", "sotto")
    assert arch.esiti(r, "livello") == ("sopra", "sotto")
    # Un consenso sull'anno (l'HICP) dice dell'anno, e niente del mese.
    assert arch.esiti(r, "anno") == (None, "sopra")
    assert arch.esiti(None, "periodo") == (None, None)


def test_la_misura_delle_etichette() -> None:
    assert arch.misura("US CPI release") == "periodo"
    assert arch.misura("Eurozone HICP flash") == "anno"
    assert arch.misura("US Unemployment Rate") == "livello"
    assert arch.misura("ZEW Economic Sentiment (DE)") == "livello"


# ── il riempimento e il job ───────────────────────────────────────────────


def test_il_riempimento_legge_solo_i_feriali(db: Session) -> None:
    assert bf.giorni_feriali(date(2026, 9, 11), date(2026, 9, 14)) == [date(2026, 9, 11), date(2026, 9, 14)]
    letti: list[date] = []

    def leggi(g: date):
        letti.append(g)
        return [MESE, ANNO] if g == date(2026, 9, 11) else []

    n, mancanti = bf.run(date(2026, 9, 11), date(2026, 9, 14), pausa=0, leggi=leggi, db=db)
    assert (n, mancanti, letti) == (1, [], [date(2026, 9, 11), date(2026, 9, 14)])


def test_il_job_non_si_ferma_se_una_fonte_e_giu(monkeypatch, db: Session) -> None:
    class _Ctx:
        def __enter__(self):
            return db

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(job.db_module, "SessionLocal", lambda: _Ctx())

    def ff_giu(_db):
        raise RuntimeError("feed giu'")

    giorni_letti: list[list[date]] = []

    def nasdaq(_db, giorni):
        giorni_letti.append(giorni)
        return 2, [giorni[0]]

    monkeypatch.setattr(job.macro_consenso_service, "archivia", ff_giu)
    monkeypatch.setattr(job.macro_consenso_service, "archivia_nasdaq", nasdaq)
    job.run_archivia_consenso_macro()
    assert len(giorni_letti) == 1 and len(giorni_letti[0]) == job.GIORNI_NASDAQ
    assert giorni_letti[0] == sorted(giorni_letti[0])

    def nasdaq_giu(_db, giorni):
        raise RuntimeError("503")

    monkeypatch.setattr(job.macro_consenso_service, "archivia", lambda _db: 1)
    monkeypatch.setattr(job.macro_consenso_service, "archivia_nasdaq", nasdaq_giu)
    job.run_archivia_consenso_macro()  # non solleva


def test_il_comando_passa_le_date_e_stampa_i_mancanti(monkeypatch, capsys) -> None:
    visti: list = []

    def run(dal, al, *, pausa):
        visti.append((dal, al, pausa))
        return 7, [date(2024, 3, 4)]

    monkeypatch.setattr(bf, "run", run)
    monkeypatch.setattr("sys.argv", ["backfill", "--dal", "2024-01-01", "--al", "2024-03-31", "--pausa", "0"])
    bf.main()
    assert visti == [(date(2024, 1, 1), date(2024, 3, 31), 0.0)]
    assert "7 rilasci" in capsys.readouterr().out
