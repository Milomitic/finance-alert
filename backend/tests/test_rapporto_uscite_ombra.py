"""Il rapporto delle uscite in prova silenziosa (FA-141)."""
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, OhlcvDaily, PlanOutcome, Stock
from app.scripts import rapporto_uscite_ombra as r
from app.services import uscite_ombra_service as uo
from app.services.plan_outcome_service import PLAN_METHOD_VERSION

D0 = date(2026, 3, 2)


def test_i_blocchi_contano_come_independent_blocks():
    from app.stats.sizing import independent_blocks

    date_ = [D0 + timedelta(days=k) for k in (0, 1, 2, 30, 31, 90)]
    b = r.blocchi(date_, 5)
    assert len(set(b)) == independent_blocks(date_, 5)
    assert b[0] == b[1] == b[2] and b[3] == b[4] and b[5] != b[3]


def test_il_confronto_e_appaiato_per_blocco():
    date_ = [D0 + timedelta(days=30 * k) for k in range(4)]
    c = r.confronto([1.0, 1.0, 2.0, 2.0], date_, 5)
    assert (c["n"], c["finestre"], c["media_r"]) == (4, 4, 1.5)
    assert c["t_blocchi"] > 2
    assert r.confronto([], [], 5) == {"n": 0}


def test_il_rapporto_legge_parita_e_controllo(db):
    titoli = []
    for k in range(8):
        s = Stock(ticker=f"U{k}", exchange="X", name=f"U{k}")
        db.add(s)
        db.flush()
        titoli.append(s)
        prezzo = 100.0
        for i in range(60):
            g = D0 + timedelta(days=i)
            # Sale di 1 al giorno per 30 sedute, poi scende di 2: dopo +1R il
            # pareggio esce a zero, la regola di oggi va allo stop.
            prezzo += 1.0 if i < 30 else -2.0
            db.add(OhlcvDaily(stock_id=s.id, date=g, open=prezzo, high=prezzo + 1,
                              low=prezzo - 1, close=prezzo, volume=1))
    s = titoli[0]
    a = Alert(stock_id=s.id, signal_name="trend_pullback", trigger_price=1.0,
              triggered_at=datetime(2026, 3, 1, tzinfo=UTC), snapshot="{}")
    db.add(a)
    db.flush()
    ingresso = D0 + timedelta(days=20)
    db.add(PlanOutcome(
        alert_id=a.id, stock_id=s.id, detector="trend_pullback", signal_date=ingresso,
        tone="bull", horizon_days=21, entry_date=ingresso, entry=121.0, stop=111.0,
        tp1=171.0, tp2=None, r=10.0, esito="stop", resolved_date=ingresso,
        bars_to_outcome=1, r_multiple=-1.0, mae_r=0.0, mfe_r=0.0, tp2_reached=False,
        method_version=PLAN_METHOD_VERSION, legs_window_complete=True,
        matured_at=datetime.now(UTC)))
    db.commit()
    uo.matura(db)
    out = r.rapporto(db)
    assert out["trade"] == 1
    assert out["parita"] == {"coincidono": 1, "su": 1}
    voce = out["varianti"]["pareggio_1r"]["trend_pullback@21"]
    assert voce["segnali"]["n"] == 1 and voce["segnali"]["media_r"] == 1.0
    assert voce["controllo"]["n"] == 1
    senza = r.rapporto(db, con_controllo=False)
    assert "controllo" not in senza["varianti"]["pareggio_1r"]["trend_pullback@21"]


def test_main_stampa_il_rapporto(db, monkeypatch, capsys):
    import contextlib
    import json
    import sys

    @contextlib.contextmanager
    def sessione():
        yield db

    monkeypatch.setattr(r, "SessionLocal", sessione)
    monkeypatch.setattr(sys, "argv", ["rapporto", "--senza-controllo"])
    r.main()
    assert json.loads(capsys.readouterr().out)["trade"] == 0
