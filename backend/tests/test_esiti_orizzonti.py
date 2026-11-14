"""`esiti_orizzonti`: ogni alert a piu' orizzonti, col controllo abbinato
(FA-138, FA-139), e il tasso a pesi uguali per giorno (FA-140)."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
from sqlalchemy import select

from app.models import Alert, EsitoOrizzonte, OhlcvDaily, Stock
from app.services import esiti_orizzonti_service as eo
from app.services import signal_outcome_service as sos
from app.stats.sizing import tasso_per_giorno

D0 = date(2026, 1, 5)
BARRE = 60


# ─── Il controllo: perche' la mediana ───────────────────────────────────────

def _sorteggi(n: int, seme: int) -> list[tuple[float, list[float]]]:
    """Rendimenti lognormali: asimmetrici a destra come quelli veri."""
    rng = np.random.default_rng(seme)
    out = []
    for _ in range(n):
        r = np.exp(rng.normal(0, 0.4, 6)) - 1.0
        out.append((float(r[0]), [float(x) for x in r[1:]]))
    return out


def test_sotto_ipotesi_nulla_il_colpo_sul_controllo_vale_cinquanta():
    """Sei estrazioni scambiabili: P(prima > mediana delle altre cinque) = 3/6,
    qualunque sia la distribuzione. Vale per entrambi i toni."""
    s = _sorteggi(20_000, 1)
    for tono in ("bull", "bear"):
        colpi = [eo.contro_il_controllo(r, c, tono)[2] for r, c in s]
        assert abs(np.mean(colpi) - 0.5) < 0.012, tono


def test_controllo_negativo_contro_la_media_il_colpo_non_vale_cinquanta():
    """Lo stesso confronto con la MEDIA dei cinque e' distorto su dati
    asimmetrici: senza questo controllo il test sopra passerebbe anche se la
    distribuzione fosse simmetrica, cioe' anche se non provasse niente."""
    s = _sorteggi(20_000, 1)
    colpi = [1 if r > float(np.mean(c)) else 0 for r, c in s]
    assert np.mean(colpi) < 0.46


def test_l_ordine_dei_controlli_e_riproducibile_e_non_dipende_dall_input():
    candidati = list(range(100, 140))
    a = eo.ordine_dei_controlli(candidati, 7)
    b = eo.ordine_dei_controlli(list(reversed(candidati)), 7)
    assert a == b
    assert a != eo.ordine_dei_controlli(candidati, 8)
    assert sorted(a) == candidati


def test_eccesso_sul_controllo_ha_il_segno_del_tono():
    assert eo.contro_il_controllo(0.10, [0, 0, 0.02, 0.05, 0.06], "bull") == (0.02, 0.08, 1)
    med, ecc, colpo = eo.contro_il_controllo(0.10, [0, 0, 0.02, 0.05, 0.06], "bear")
    assert (med, colpo) == (0.02, 0) and abs(ecc + 0.08) < 1e-12


# ─── La maturazione, su un universo seminato ────────────────────────────────

def _universo(db, n: int, *, stessa_vol: bool = False, seme: int = 3) -> list[Stock]:
    rng = random.Random(seme)
    titoli = []
    passi = [rng.gauss(0, 0.02) for _ in range(BARRE)]
    for k in range(n):
        s = Stock(ticker=f"T{k:02d}", exchange="NASDAQ", name=f"Titolo {k}", country="US")
        db.add(s)
        db.flush()
        prezzo = 50.0 + k
        scala = 1.0 if stessa_vol else 0.5 + k / n
        for i in range(BARRE):
            passo = passi[i] if stessa_vol else rng.gauss(0, 0.02 * scala)
            prezzo *= 1 + passo
            db.add(OhlcvDaily(stock_id=s.id, date=D0 + timedelta(days=i), open=prezzo,
                              high=prezzo * 1.01, low=prezzo * 0.99, close=prezzo, volume=1e6))
        titoli.append(s)
    return titoli


def _alert(db, s: Stock, *, nato: int, segnale: int, detector: str = "trend_pullback",
           tono: str = "bull") -> Alert:
    a = Alert(
        stock_id=s.id, trigger_price=1.0, signal_name=detector,
        signal_date=D0 + timedelta(days=segnale),
        snapshot=json.dumps({"tone": tono,
                             "first_emitted_at": f"{D0 + timedelta(days=nato)}T23:30:00+00:00"}),
    )
    db.add(a)
    db.flush()
    return a


def test_matura_gli_orizzonti_trascorsi_dall_ancora_di_emissione(db):
    titoli = _universo(db, 40)
    # Comparso al giorno 30, poi rivisto fino al 35: la misura parte dal 30.
    a = _alert(db, titoli[0], nato=30, segnale=35)
    db.commit()

    scritte = eo.matura(db, eta_massima_giorni=None)
    righe = {r.orizzonte: r for r in db.execute(select(EsitoOrizzonte)).scalars()}
    assert scritte == 3
    assert set(righe) == {1, 5, 21}          # 30 + 63 oltre le 60 barre
    giorno = D0 + timedelta(days=30)
    chiusure = [float(b.close) for b in db.execute(
        select(OhlcvDaily).where(OhlcvDaily.stock_id == titoli[0].id).order_by(OhlcvDaily.date)
    ).scalars()]
    r5 = righe[5]
    assert r5.ancora == giorno and r5.alert_id == a.id
    assert r5.ingresso == chiusure[30] and r5.uscita == chiusure[35]

    # Il riferimento di mercato e' quello del magazzino esistente.
    societa = sos._load_universe_closes(db)
    assert r5.mediana_universo == sos._universe_fwd_medians(societa, 5)[giorno]
    assert all(r.controlli_n == eo.CONTROLLI and r.colpo_controllo in (0, 1)
               for r in righe.values())

    # Idempotente, e il 63 non c'e' ancora: non si inventa.
    assert eo.matura(db, eta_massima_giorni=None) == 0


def test_un_titolo_con_un_alert_dello_stesso_detector_non_fa_da_controllo(db):
    """Volatilita' identica: tutti nella stessa fascia. Con 27 dei 31 vicini
    occupati da un alert dello stesso detector restano 4 candidati, meno dei
    cinque che servono: niente controllo, invece di un controllo piu' piccolo
    che cambierebbe il 50% dell'ipotesi nulla."""
    titoli = _universo(db, 32, stessa_vol=True)
    _alert(db, titoli[0], nato=30, segnale=30)
    for s in titoli[1:28]:
        _alert(db, s, nato=28, segnale=33)
    db.commit()
    eo.matura(db, eta_massima_giorni=None)
    riga = db.execute(select(EsitoOrizzonte).where(
        EsitoOrizzonte.stock_id == titoli[0].id, EsitoOrizzonte.orizzonte == 5,
    )).scalars().one()
    assert riga.controllo is None and riga.colpo_controllo is None
    assert riga.colpo_mediana is not None


def test_un_alert_di_un_altro_detector_non_esclude(db):
    titoli = _universo(db, 32, stessa_vol=True)
    _alert(db, titoli[0], nato=30, segnale=30)
    for s in titoli[1:28]:
        _alert(db, s, nato=28, segnale=33, detector="sr_flip")
    db.commit()
    eo.matura(db, eta_massima_giorni=None)
    riga = db.execute(select(EsitoOrizzonte).where(
        EsitoOrizzonte.stock_id == titoli[0].id, EsitoOrizzonte.orizzonte == 5,
    )).scalars().one()
    assert riga.controlli_n == eo.CONTROLLI


def test_un_tono_non_determinato_non_si_misura(db):
    titoli = _universo(db, 32)
    _alert(db, titoli[0], nato=30, segnale=30, tono="undetermined")
    db.commit()
    assert eo.matura(db, eta_massima_giorni=None) == 0


# ─── La lettura ─────────────────────────────────────────────────────────────

def test_il_tasso_per_giorno_non_si_fa_dominare_da_un_giorno_affollato():
    affollato = [(D0, 1)] * 300
    calmi = [(D0 + timedelta(days=k), 0) for k in range(1, 31)]
    tasso, giorni = tasso_per_giorno(affollato + calmi)
    assert giorni == 31
    assert tasso == round(1 / 31 * 100, 1)
    assert tasso_per_giorno([]) == (None, 0)


def test_il_verdetto_si_da_solo_all_orizzonte_proprio():
    righe = [SimpleNamespace(ancora=D0 + timedelta(days=7 * k), colpo_mediana=1,
                             colpo_controllo=1, eccesso_controllo=0.01) for k in range(200)]
    proprio = eo.cella(righe, 5, True, 30)
    altro = eo.cella(righe, 5, False, 30)
    assert proprio["verdetto"] == "above"
    assert altro["verdetto"] is None
    assert proprio["colpo_controllo"] == altro["colpo_controllo"] == 100.0
    assert proprio["eccesso_controllo_medio"] == 1.0


def test_la_parita_col_magazzino_esistente_regge(db, monkeypatch):
    """Lo script di riempimento confronta le due tabelle all'orizzonte proprio:
    stessa aritmetica, stesso numero."""
    from app.core.provenance import OUTCOME_METHOD_VERSION
    from app.models import SignalOutcome
    from app.scripts import backfill_esiti_orizzonti as script

    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 5)
    titoli = _universo(db, 40)
    a = _alert(db, titoli[0], nato=30, segnale=30)
    db.commit()
    sos.mature_outcomes(db)
    eo.matura(db, eta_massima_giorni=None)
    o = db.execute(select(SignalOutcome)).scalars().one()
    assert o.method_version == OUTCOME_METHOD_VERSION and o.alert_id == a.id
    p = script.parita(db)
    assert (p["confrontati"], p["discordi"], p["deriva_mediana"]) == (1, 0, 0)

    # Controllo negativo: a parita' di ingressi un colpo diverso e' un difetto.
    o.mkt_neutral_hit = 1 - o.mkt_neutral_hit
    db.commit()
    assert script.parita(db)["discordi"] == 1

    # Una mediana cambiata dopo la maturazione e' deriva dei dati, non un
    # difetto di questo codice: si conta a parte, e cambia il colpo.
    o.universe_mean_fwd += 0.5
    db.commit()
    p = script.parita(db)
    assert (p["discordi"], p["deriva_mediana"]) == (0, 1)


def test_lo_script_riempie_e_rende_zero_quando_la_parita_regge(db, monkeypatch, capsys):
    from contextlib import nullcontext

    import app.core.db as dbm
    from app.scripts import backfill_esiti_orizzonti as script

    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 5)
    titoli = _universo(db, 40)
    _alert(db, titoli[0], nato=30, segnale=30)
    db.commit()
    sos.mature_outcomes(db)
    monkeypatch.setattr(dbm, "SessionLocal", lambda: nullcontext(db))
    assert script.main() == 0
    out = capsys.readouterr().out
    assert "righe scritte ora: 3" in out and "1 confrontati, 0 discordi a parita' di ingressi" in out
