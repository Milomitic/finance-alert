"""I modelli in prova silenziosa: addestramento, punteggi, valutazione.

Nessuno di questi numeri raggiunge il motore: i test verificano che vengano
calcolati, salvati e letti, e che un guasto non tocchi mai uno scan.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ml import addestramento, ombra, valutazione
from app.ml.caratteristiche import matrice, nomi_volatilita, riga_selezione, riga_volatilita
from app.ml.gbm import GBM
from app.models import Alert, OhlcvDaily, Stock
from app.models.modello_ombra import ModelloOmbra

_ADESSO = datetime(2026, 9, 1, tzinfo=UTC)


def _feriali(n: int, fine: date = date(2026, 8, 28)) -> list[date]:
    out, d = [], fine
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def _catalogo(db, titoli: int = 4, barre: int = 700, seme: int = 1) -> list[Stock]:
    rng = np.random.default_rng(seme)
    giorni = _feriali(barre)
    out = []
    for k in range(titoli):
        s = Stock(ticker=f"ML{k}", exchange="NASDAQ", name=f"ML {k}", country="US")
        db.add(s)
        db.flush()
        vol = 0.015 * np.exp(np.cumsum(rng.normal(0, 0.05, barre)) * 0.1)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 1, barre) * vol))
        for i, d in enumerate(giorni):
            r = c[i] * vol[i] * rng.uniform(0.5, 2)
            db.add(OhlcvDaily(stock_id=s.id, date=d, open=c[i] * (1 + rng.normal(0, vol[i] / 3)),
                              high=c[i] + r / 2, low=c[i] - r / 2, close=c[i],
                              volume=float(rng.integers(100_000, 1_000_000))))
        out.append(s)
    db.commit()
    return out


# ─── il GBM ────────────────────────────────────────────────────────────────

def test_il_gbm_impara_e_il_giro_json_e_l_identita() -> None:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(4000, 5))
    X[rng.random(X.shape) < 0.05] = np.nan
    y = (np.nan_to_num(X[:, 0]) + 0.3 * rng.normal(size=4000) > 0).astype(float)
    g = GBM(n_trees=60, depth=3, lr=0.1, min_leaf=50).fit(X, y)
    p = g.predict(X)
    # Impara davvero: la variabile 0 decide, e il modello la separa.
    assert p[X[:, 0] > 1].mean() > 0.8 > 0.2 > p[X[:, 0] < -1].mean()
    assert g.importanza(5).argmax() == 0
    g2 = GBM.from_dict(json.loads(json.dumps(g.to_dict())))
    assert np.allclose(g2.predict(X), p)


def test_il_gbm_quadratico_stima_una_media() -> None:
    rng = np.random.default_rng(1)
    X = rng.normal(size=(3000, 3))
    y = 2.0 * (X[:, 1] > 0) + rng.normal(0, 0.1, 3000)
    g = GBM(n_trees=80, depth=2, lr=0.2, min_leaf=50, loss="l2").fit(X, y)
    assert g.predict(np.array([[0.0, 2.0, 0.0]]))[0] == pytest.approx(2.0, abs=0.2)
    assert g.predict(np.array([[0.0, -2.0, 0.0]]))[0] == pytest.approx(0.0, abs=0.2)


# ─── le variabili ──────────────────────────────────────────────────────────

def test_la_matrice_si_costruisce_per_nome() -> None:
    righe = [{"a": 1.0, "det_x": 1.0}, {"b": 2.0}]
    X = matrice(righe, ["b", "a", "det_x"], zero_se_manca=("det_",))
    assert np.isnan(X[0, 0]) and X[0, 1] == 1.0 and X[0, 2] == 1.0
    # Un detector assente e' un «no», una variabile assente e' «non noto».
    assert X[1, 0] == 2.0 and np.isnan(X[1, 1]) and X[1, 2] == 0.0


def test_le_direzionali_portano_il_segno_del_segnale() -> None:
    ctx = {"ret_21": 0.10, "rsi14": 70.0, "atr_pct": 0.02, "vol20": 0.01}
    kw = dict(detector="sr_flip", horizon="medium", strength=70, factors={"k": 0.5},
              ctx=ctx, stop_atr=2.5, rr=2.0)
    toro, orso = riga_selezione(tone="bull", **kw), riga_selezione(tone="bear", **kw)
    assert toro["s_ret_21"] == pytest.approx(0.10) and orso["s_ret_21"] == pytest.approx(-0.10)
    assert toro["s_rsi"] == pytest.approx(20.0) and orso["s_rsi"] == pytest.approx(-20.0)
    assert toro["det_sr_flip"] == 1.0 and toro["fac_k"] == 0.5 and toro["hz"] == 1.0
    assert riga_volatilita(ctx)["vol20_su_atr"] == pytest.approx(0.5)
    assert "vol20_su_atr" in nomi_volatilita()


def test_il_bersaglio_di_volatilita_e_l_escursione_futura_sull_atr(db) -> None:
    (s,) = _catalogo(db, titoli=1, barre=300)
    df = addestramento._barre(db, s.id)
    righe = addestramento.righe_volatilita(df, passo=1000, dal="1900-01-01")
    assert len(righe) == 1
    giorno, x, y = righe[0]
    t = addestramento.FINESTRA - 1
    assert giorno == df["date"].iat[t]
    esc = (df["high"] - df["low"]).iloc[t + 1:t + 11].mean()
    atr = x["atr_pct"] * df["close"].iat[t]
    assert y == pytest.approx(math.log(esc / atr), rel=1e-4)


def test_il_controllo_e_lo_stesso_piano_in_unita_del_suo_atr() -> None:
    from app.signals.trade_plan import costruisci_piano

    piano = costruisci_piano({"tone": "bear", "atr": 2.0, "invalidation": {"level": 106.0},
                              "horizon": "medium"}, 100.0, "sr_flip")
    ctrl = addestramento._piano_di_controllo(piano, atr_o=0.5, entry_o=20.0, atr=2.0)
    assert ctrl.side == "short" and ctrl.entry == 20.0
    assert ctrl.r / 0.5 == pytest.approx(piano.r / 2.0)
    assert ctrl.stop > ctrl.entry
    assert [t.rr for t in ctrl.targets] == [t.rr for t in piano.targets]
    assert all(t.price < ctrl.entry for t in ctrl.targets)


# ─── addestramento, lettura, valutazione ───────────────────────────────────

@pytest.fixture
def addestrato(db):
    titoli = _catalogo(db)
    metriche = addestramento.addestra(
        db, n_titoli_vol=4, n_titoli_sel=3, passo_vol=5, passo_sel=60, anni=3,
        adesso=_ADESSO, min_righe_vol=50, min_righe_sel=50)
    return titoli, metriche


def test_l_addestramento_salva_due_modelli_con_le_metriche(db, addestrato) -> None:
    _, metriche = addestrato
    assert set(metriche) == {"volatilita", "selezione"}
    righe = db.query(ModelloOmbra).all()
    assert {r.nome for r in righe} == {"volatilita", "selezione"}
    for r in righe:
        art = json.loads(r.artefatto)
        assert art["nomi"] and art["gbm"]["trees"]
        assert json.loads(r.metriche)["righe"] > 0
    sel = next(r for r in righe if r.nome == "selezione")
    assert 0 < json.loads(sel.artefatto)["soglia_top30"] < 1


def test_serve_addestrare_solo_se_manca_o_e_vecchio(db, addestrato) -> None:
    assert addestramento.serve_addestrare(db, adesso=_ADESSO + timedelta(days=5)) is False
    assert addestramento.serve_addestrare(db, adesso=_ADESSO + timedelta(days=28)) is True


def test_senza_modelli_si_addestra(db) -> None:
    assert addestramento.serve_addestrare(db) is True


def test_i_punteggi_vengono_dal_modello_salvato(db, addestrato) -> None:
    ombra.dimentica()
    ctx = {"atr_pct": 0.02, "vol20": 0.015, "ret_21": 0.05, "rsi14": 55.0}
    p = ombra.punteggi(db, detector="sr_flip", tone="bull", horizon="medium", strength=70,
                       factors={}, ctx=ctx, stop_atr=2.5, rr=2.0)
    assert p["vol"]["fattore"] > 0
    assert 0 < p["sel"]["p"] < 1 and isinstance(p["sel"]["top30"], bool)
    assert p["vol"]["versione"] == p["sel"]["versione"] == "2026-09-01T0000"


def test_senza_modelli_i_punteggi_sono_vuoti(db) -> None:
    assert ombra.punteggi(db, detector="sr_flip", tone="bull", horizon="medium",
                          strength=70, factors={}, ctx={"atr_pct": 0.02},
                          stop_atr=2.0, rr=2.0) == {}


def test_un_artefatto_rotto_non_rompe_niente(db) -> None:
    db.add(ModelloOmbra(nome="volatilita", versione="rotto", artefatto="{non json"))
    db.commit()
    assert ombra.punteggi(db, detector="sr_flip", tone="bull", horizon="medium",
                          strength=70, factors={}, ctx={"atr_pct": 0.02},
                          stop_atr=2.0, rr=2.0) == {}


def test_la_valutazione_misura_la_volatilita_sugli_alert_maturati(db, addestrato) -> None:
    titoli, _ = addestrato
    s = titoli[0]
    giorno = date(2026, 8, 3)
    snap = {"tone": "bull", "first_emitted_at": f"{giorno}T23:30:00+00:00", "first_atr": 1.5,
            "first_ombra": {"vol": {"fattore": 1.1, "versione": "v"},
                            "sel": {"p": 0.6, "top30": True, "versione": "v"}}}
    db.add(Alert(stock_id=s.id, signal_name="sr_flip", signal_date=giorno,
                 triggered_at=datetime(2026, 8, 3, tzinfo=UTC), trigger_price=100.0,
                 snapshot=json.dumps(snap)))
    db.commit()
    r = valutazione.rapporto(db)
    assert r["volatilita"]["n"] == 1
    assert set(r["modelli"]) == {"volatilita", "selezione"}
    assert r["selezione"]["top30"]["mercato"]["n"] == 0   # nessun esito maturato ancora


def test_il_job_salta_durante_una_scansione(monkeypatch) -> None:
    from app.scheduler.jobs import modelli_ombra as job
    from app.services import scan_lock

    chiamate = []
    monkeypatch.setattr(scan_lock, "is_running", lambda: True)
    monkeypatch.setattr(addestramento, "addestra", lambda db: chiamate.append(1))
    job.run_addestra_modelli_ombra()
    assert chiamate == []


def test_il_job_addestra_quando_serve(db, monkeypatch) -> None:
    from app.core import db as db_module
    from app.scheduler.jobs import modelli_ombra as job
    from app.services import scan_lock

    chiamate = []
    monkeypatch.setattr(scan_lock, "is_running", lambda: False)
    monkeypatch.setattr(db_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(addestramento, "addestra", lambda d: chiamate.append(1))
    job.run_addestra_modelli_ombra()
    assert chiamate == [1]


def test_df_di_prova_regge() -> None:
    """Pavimento: senza, un catalogo sintetico vuoto renderebbe vuoti tutti i
    test sopra per ragioni sbagliate."""
    assert len(_feriali(700)) == 700
    assert isinstance(pd.Timestamp(_feriali(1)[0]), pd.Timestamp)


# ─── le metriche dell'anno tenuto da parte ─────────────────────────────────

def _righe_sintetiche(n: int, seme: int = 0) -> list[dict]:
    """Match finti su tre anni: la variabile `s_ret_21` decide la skill, la
    Forza no — lo stesso verdetto dello studio, scritto a mano."""
    rng = np.random.default_rng(seme)
    inizio = date(2023, 9, 1)
    out = []
    for i in range(n):
        x = {"s_ret_21": float(rng.normal()), "det_sr_flip": 1.0, "strength": float(rng.uniform(60, 99))}
        skill = x["s_ret_21"] + rng.normal(0, 1.0)
        out.append({"date": (inizio + timedelta(days=int(i * 1095 / n))).isoformat(),
                    "detector": "sr_flip", "strength": x["strength"], "R": skill, "Rc": 0.0, "x": x})
    return out


def test_le_metriche_di_selezione_si_misurano_solo_dopo_il_taglio() -> None:
    art, met = addestramento.modello_selezione(_righe_sintetiche(6000), taglio="2025-09-01")
    assert met["righe_prova"] > 200 and met["mesi"] >= 10
    # Il modello vede la variabile che decide, la Forza no.
    assert met["auc"] > 0.6 and abs(met["auc_forza"] - 0.5) < 0.05
    assert met["skill_top30"] > met["skill_tutti"]
    assert met["t_mensile"] > 3
    assert art["soglia_top30"] > 0


def test_le_metriche_di_volatilita_battono_l_atr_quando_c_e_da_battere() -> None:
    rng = np.random.default_rng(3)
    righe = []
    for i in range(4000):
        v = float(rng.uniform(0.005, 0.04))
        ctx = {"atr_pct": 0.02, "vol20": v}
        # L'escursione futura segue vol20, non l'ATR: il modello deve vederlo.
        y = math.log(v / 0.02) + float(rng.normal(0, 0.1))
        righe.append(((date(2023, 9, 1) + timedelta(days=i * 1095 // 4000)).isoformat(),
                      riga_volatilita(ctx), y))
    _, met = addestramento.modello_volatilita(righe, taglio="2025-09-01")
    assert met["R2_contro_ATR"] > 0.5


def test_auc_e_t_mensile_sui_casi_limite() -> None:
    assert addestramento._auc(np.array([1, 0, 1, 0]), np.array([0.9, 0.1, 0.8, 0.2])) == 1.0
    assert addestramento._auc(np.array([1, 1]), np.array([0.3, 0.4])) is None
    assert addestramento._t_mensile(pd.Series([0.1, 0.1])) is None
    assert addestramento._t_mensile(pd.Series([0.1, 0.2, 0.3])) == pytest.approx(0.2 / (0.1 / math.sqrt(3)))


def test_gli_script_stampano_json(db, monkeypatch, capsys) -> None:
    from app.core import db as db_module
    from app.scripts import addestra_modelli_ombra, rapporto_modelli_ombra

    class _Sessione:
        def __enter__(self):
            return db

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(db_module, "SessionLocal", lambda: _Sessione())
    rapporto_modelli_ombra.main()
    assert json.loads(capsys.readouterr().out)["volatilita"] == {"n": 0}
    monkeypatch.setattr(addestramento, "addestra", lambda d: {"volatilita": {"righe": 1}})
    addestra_modelli_ombra.main()
    assert json.loads(capsys.readouterr().out) == {"volatilita": {"righe": 1}}
