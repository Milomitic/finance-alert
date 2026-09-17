"""Il magazzino degli esiti di piano: forma, vincoli e valori che ci entrano.

`plan_outcomes` sta ACCANTO a `signal_outcomes`, non dentro, e la ragione e'
temporale prima che concettuale: una riga di `signal_outcomes` nasce solo
quando l'orizzonte fisso e' trascorso — per `analyst_momentum` sono 63 sedute —
mentre un esito di piano si risolve quando stop o target vengono toccati, cioe'
di regola PRIMA. Appendere le colonne nuove a quella tabella le farebbe
aspettare l'orizzonte, riproducendo esattamente il difetto che questo lavoro
chiude.

⚠️ Il primo gruppo di test e' quello che in questo repo ha gia' fermato la
produzione per ~19 ore: una costante piu' lunga della sua colonna. Postgres
rifiuta il valore, SQLite lo accetta perche' li' la lunghezza di un VARCHAR e'
decorativa — quindi la suite era verde mentre ogni scansione falliva. Si
confrontano le COSTANTI IMPORTATE, mai stringhe ricopiate qui: una copia
resterebbe giusta anche dopo che qualcuno ha allungato il valore vero.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Alert, PlanOutcome, Stock
from app.models.plan_outcome import FONTE_EMESSO, FONTE_RICOSTRUITO
from app.services.plan_outcome_service import ESITI


def _lunghezza(colonna: str) -> int:
    lunghezza = PlanOutcome.__table__.c[colonna].type.length
    assert lunghezza is not None, f"plan_outcomes.{colonna} non dichiara una lunghezza"
    return lunghezza


def _non_entrano(colonna: str, valori: tuple[str, ...]) -> list[str]:
    limite = _lunghezza(colonna)
    return [f"{v!r} ({len(v)} > {limite})" for v in valori if len(v) > limite]


# ─── 1. I valori entrano nelle colonne ─────────────────────────────────────

def test_ogni_esito_entra_nella_sua_colonna() -> None:
    troppo_lunghi = _non_entrano("esito", tuple(sorted(ESITI)))
    assert not troppo_lunghi, f"esiti che non entrano in plan_outcomes.esito: {troppo_lunghi}"


def test_ogni_fonte_entra_nella_sua_colonna() -> None:
    troppo_lunghi = _non_entrano("source", (FONTE_EMESSO, FONTE_RICOSTRUITO))
    assert not troppo_lunghi, f"fonti che non entrano in plan_outcomes.source: {troppo_lunghi}"


def test_gli_esiti_sono_quelli_che_la_gara_sa_produrre() -> None:
    """⚠️ Pavimento sull'insieme, non solo sulla lunghezza.

    Senza, svuotare `ESITI` renderebbe verde il test sulla lunghezza — e'
    la forma «un test puo' essere vero di niente». E se qualcuno aggiunge un
    esito alla gara senza pensarci, qui se ne accorge.
    """
    assert {"tp1", "stop", "ambigua", "scaduto"} == ESITI


# ─── 2. Un esito per alert, e non due ──────────────────────────────────────

def _alert(db: Session, ticker: str = "AAA") -> Alert:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Corp", country="US")
    db.add(s)
    db.flush()
    a = Alert(stock_id=s.id, signal_name="sr_flip", signal_date=date(2026, 3, 1),
              triggered_at=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
              trigger_price=100.0, snapshot="{}")
    db.add(a)
    db.flush()
    return a


def _riga(alert: Alert, **kw) -> PlanOutcome:
    base = dict(
        alert_id=alert.id, stock_id=alert.stock_id, detector="sr_flip",
        signal_date=date(2026, 3, 1), tone="bull", horizon_days=21,
        entry_date=date(2026, 3, 2), entry=100.0, stop=96.0, tp1=108.0, tp2=112.0,
        r=4.0, esito="tp1", resolved_date=date(2026, 3, 10), bars_to_outcome=6,
        r_multiple=2.0, mae_r=0.25, mfe_r=2.25, tp2_reached=False,
        source=FONTE_EMESSO, method_version="1", matured_at=datetime.now(UTC),
    )
    return PlanOutcome(**{**base, **kw})


def test_una_riga_si_scrive_e_si_rilegge(db: Session) -> None:
    a = _alert(db)
    db.add(_riga(a))
    db.flush()

    letta = db.query(PlanOutcome).one()
    assert letta.esito == "tp1"
    assert letta.r_multiple == pytest.approx(2.0)
    assert letta.tp2_reached is False


def test_due_esiti_per_lo_STESSO_alert_sono_rifiutati(db: Session) -> None:
    """La maturazione deve poter girare a ogni scansione senza duplicare.

    L'idempotenza vive nel VINCOLO, non nella diligenza del chiamante: un
    controllo «esiste gia'?» in Python ha una finestra di corsa, e un magazzino
    d'efficacia con righe doppie conta due volte lo stesso trade — cioe'
    riporta un campione piu' grande di quello che ha, che e' il difetto che
    questo progetto tiene d'occhio piu' di ogni altro.
    """
    a = _alert(db)
    db.add(_riga(a))
    db.flush()
    db.add(_riga(a, esito="stop", r_multiple=-1.0))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_alert_diversi_convivono(db: Session) -> None:
    a1 = _alert(db, "AAA")
    a2 = _alert(db, "BBB")
    db.add(_riga(a1))
    db.add(_riga(a2, esito="stop", r_multiple=-1.0))
    db.flush()
    assert db.query(PlanOutcome).count() == 2


# ─── 3. La geometria e' CONGELATA, non ricalcolabile ───────────────────────

def test_la_riga_porta_la_geometria_usata_e_non_solo_l_esito(db: Session) -> None:
    """⚠️ Entrata, stop, target e R si scrivono nella riga anche se sarebbero
    ricalcolabili dallo snapshot.

    Perche': la geometria e' tarata (le tabelle `HZ`, il tetto a 8 ATR, il
    pavimento) e quelle costanti cambieranno. Una riga che rimandasse al
    calcolo verrebbe riletta domani con una geometria diversa da quella che ha
    prodotto l'esito, e il magazzino direbbe cose che non sono mai successe.
    `method_version` accanto dice CON QUALE regola e' stata scritta.
    """
    a = _alert(db)
    db.add(_riga(a))
    db.flush()

    letta = db.query(PlanOutcome).one()
    for campo in ("entry", "stop", "tp1", "tp2", "r"):
        assert getattr(letta, campo) is not None, f"{campo} non e' congelato nella riga"
    assert letta.method_version


# ─── 4. La migrazione, andata E ritorno ────────────────────────────────────

def test_la_migrazione_crea_e_ripercorre_su_sqlite(tmp_path, monkeypatch) -> None:
    """⚠️ Il RITORNO si prova, non si presume.

    Una migrazione che non si ripercorre all'indietro va scoperta adesso, non
    durante un ripristino — il drill del lunedi' esiste per questa ragione.

    ⚠️ E l'url si cambia su `settings`, non sul `Config`: `alembic/env.py` fa
    `config.set_main_option("sqlalchemy.url", settings.database_url)`
    INCONDIZIONATAMENTE, quindi passarlo al Config non ha alcun effetto e la
    migrazione girerebbe contro il database configurato. E' gia' successo: un
    test di migrazioni su Postgres non toccava Postgres e passava lo stesso.
    """
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from alembic import command
    from app.core.config import settings

    url = f"sqlite:///{tmp_path / 'prova.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = Config("alembic.ini")

    command.upgrade(cfg, "head")
    ispettore = inspect(create_engine(url))
    assert "plan_outcomes" in ispettore.get_table_names()
    indici = {i["name"]: i for i in ispettore.get_indexes("plan_outcomes")}
    # ⚠️ `bool(...)`: SQLite rende 1 e Postgres True per la stessa proprieta'.
    # Un `is True` qui sarebbe rosso su un indice perfettamente unico.
    assert bool(indici["ix_plan_outcomes_alert"]["unique"]) is True, (
        "senza unicita' la maturazione duplicherebbe a ogni scansione"
    )

    command.downgrade(cfg, "-1")
    assert "plan_outcomes" not in inspect(create_engine(url)).get_table_names()

    # E si risale: una migrazione deve reggere anche il secondo giro, che e'
    # quello che fa un ripristino seguito da un riallineamento.
    command.upgrade(cfg, "head")
    assert "plan_outcomes" in inspect(create_engine(url)).get_table_names()
