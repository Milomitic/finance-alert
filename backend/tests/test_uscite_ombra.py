"""Uscite alternative del piano in prova silenziosa (FA-141)."""
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, OhlcvDaily, PlanOutcome, PlanOutcomeOmbra, Stock
from app.services import uscite_ombra_service as uo
from app.services.plan_outcome_service import PLAN_METHOD_VERSION, Barra, corri_la_gara

V = {v.nome: v for v in uo.VARIANTI}


def _b(i, alto, basso, chiusura):
    return Barra(f"2026-01-{i:02d}", alto, basso, chiusura)


def _corri(barre, variante, orizzonte=6, lato="long"):
    return uo.corri_variante(lato=lato, ingresso=100.0, stop=90.0 if lato == "long" else 110.0,
                             tp1=130.0 if lato == "long" else 70.0, r=10.0,
                             barre=barre, orizzonte=orizzonte, variante=V[variante])


# Sale a +1,2R, poi torna giu' fino allo stop iniziale.
RITORNO = [_b(1, 112, 99, 110), _b(2, 111, 100, 105), _b(3, 104, 89, 92),
           _b(4, 95, 91, 93), _b(5, 96, 92, 94), _b(6, 97, 93, 95)]


def test_attuale_perde_un_r_il_pareggio_ne_salva_tutto():
    assert _corri(RITORNO, "attuale") == uo.EsitoVariante("stop", -1.0, 3)
    assert _corri(RITORNO, "pareggio_1r") == uo.EsitoVariante("pareggio", 0.0, 2)
    assert _corri(RITORNO, "pareggio_05r") == uo.EsitoVariante("pareggio", 0.0, 2)


def test_lo_stop_si_sposta_dalla_barra_SUCCESSIVA():
    """Nella stessa barra il massimo puo' venire dopo il minimo."""
    barre = [_b(1, 112, 89, 95)] + RITORNO[1:]
    assert _corri(barre, "pareggio_1r").esito == "stop"


def test_stop_e_target_nella_stessa_barra_e_ambigua_allo_stop():
    barre = [_b(1, 131, 89, 100)] + RITORNO[1:]
    assert _corri(barre, "attuale") == uo.EsitoVariante("ambigua", -1.0, 1)


def test_uscita_a_meta_sotto_la_soglia_e_non_sopra():
    piatto = [_b(i, 101, 99, 100.5) for i in range(1, 7)]
    assert _corri(piatto, "uscita_meta") == uo.EsitoVariante("uscita_meta", 0.05, 3)
    su = [_b(i, 104, 99, 103) for i in range(1, 7)]       # +0,3R a meta': resta
    assert _corri(su, "uscita_meta").esito == "scaduto"


def test_lo_short_e_lo_specchio():
    specchio = [_b(i, 200 - b.basso, 200 - b.alto, 200 - b.chiusura) for i, b in enumerate(RITORNO, 1)]
    assert _corri(specchio, "attuale", lato="short") == uo.EsitoVariante("stop", -1.0, 3)
    assert _corri(specchio, "pareggio_1r", lato="short").esito == "pareggio"


def test_finestra_aperta_niente():
    assert _corri(RITORNO[:4], "attuale") is None


def test_attuale_coincide_con_la_gara_vera():
    """Il controllo di parita': la variante «attuale» rifa' corri_la_gara."""
    import random

    rnd = random.Random(7)
    for _ in range(300):
        p, barre = 100.0, []
        for i in range(1, 22):
            c = p * (1 + rnd.uniform(-0.04, 0.04))
            barre.append(Barra(f"2026-02-{i:02d}", max(p, c) * 1.01, min(p, c) * 0.99, c))
            p = c
        lato = rnd.choice(["long", "short"])
        stop, tp1 = (95.0, 108.0) if lato == "long" else (105.0, 92.0)
        vera = _gara(lato, stop, tp1, barre)
        mia = uo.corri_variante(lato=lato, ingresso=100.0, stop=stop, tp1=tp1, r=5.0,
                                barre=barre, orizzonte=21, variante=V["attuale"])
        assert (mia.esito, round(mia.r_multiplo, 9), mia.barre) == vera


def _gara(lato, stop, tp1, barre):
    from types import SimpleNamespace

    t = SimpleNamespace(price=tp1, rr=abs(tp1 - 100.0) / 5.0)
    piano = SimpleNamespace(r=5.0, targets=[t], side=lato, entry=100.0, stop=stop)
    e = corri_la_gara(piano, barre, 21)
    return (e.esito, round(e.r_multiplo, 9), e.barre)


def test_matura_scrive_le_quattro_varianti_solo_a_finestra_chiusa(db):
    s = Stock(ticker="OMB", exchange="X", name="Ombra")
    db.add(s)
    db.flush()
    giorno = date(2026, 1, 1)
    for i, (alto, basso, ch) in enumerate([(100, 100, 100)] + [(b.alto, b.basso, b.chiusura) for b in RITORNO]):
        db.add(OhlcvDaily(stock_id=s.id, date=giorno + timedelta(days=i), open=ch, high=alto,
                          low=basso, close=ch, volume=1))
    ids = []
    for completa in (True, False):
        a = Alert(stock_id=s.id, signal_name="trend_pullback", trigger_price=100.0,
                  triggered_at=datetime(2026, 1, 1, tzinfo=UTC), snapshot="{}")
        db.add(a)
        db.flush()
        db.add(PlanOutcome(
            alert_id=a.id, stock_id=s.id, detector="trend_pullback", signal_date=giorno,
            tone="bull", horizon_days=6, entry_date=giorno, entry=100.0, stop=90.0, tp1=130.0,
            tp2=None, r=10.0, esito="stop", resolved_date=giorno, bars_to_outcome=3,
            r_multiple=-1.0, mae_r=1.1, mfe_r=1.2, tp2_reached=False,
            method_version=PLAN_METHOD_VERSION, legs_window_complete=completa,
            matured_at=datetime.now(UTC)))
        ids.append(a.id)
    db.commit()
    assert uo.matura(db) == 4
    righe = {r.variante: r for r in db.query(PlanOutcomeOmbra).all()}
    assert set(righe) == {"attuale", "pareggio_1r", "pareggio_05r", "uscita_meta"}
    assert {r.alert_id for r in righe.values()} == {ids[0]}
    assert righe["attuale"].r_multiple == -1.0 and righe["pareggio_1r"].esito == "pareggio"
    assert uo.matura(db) == 0          # idempotente
