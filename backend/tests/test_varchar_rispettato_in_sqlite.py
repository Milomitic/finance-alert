"""La suite fa rispettare le lunghezze `VARCHAR(n)` anche su SQLite.

Guardia del meccanismo in `conftest.enforce_varchar_lengths`. Senza questi
test, un trigger che smettesse di scattare (nome di tabella sbagliato, colonne
saltate) lascerebbe la suite verde esattamente come prima di FA-077 — cioe'
cieca proprio al difetto che ha fermato le scansioni.
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PriceAlert, Stock


def _stock(db: Session, **kw) -> Stock:
    s = Stock(ticker="VCH", exchange="NYSE", name="Varchar", **kw)
    db.add(s)
    db.commit()
    return s


def test_un_valore_troppo_lungo_viene_rifiutato_come_in_postgres(db: Session) -> None:
    # stocks.country e' VARCHAR(8): "Switzerland" ne ha 11.
    with pytest.raises(IntegrityError, match=r"stocks\.country VARCHAR\(8\)"):
        _stock(db, country="Switzerland")


def test_il_limite_esatto_passa(db: Session) -> None:
    # Controllo positivo: senza, il test sopra passerebbe anche con un
    # trigger che rifiuta tutto.
    s = _stock(db, country="A" * 8)
    assert s.id is not None


def test_vale_anche_per_gli_update(db: Session) -> None:
    s = _stock(db, country="US")
    s.country = "United States"
    with pytest.raises(IntegrityError):
        db.commit()


def test_i_trigger_coprono_tutte_le_colonne_di_lunghezza_fissa(db: Session) -> None:
    from sqlalchemy import String, text

    from app.core.db import Base

    attese = {
        f"varchar_{t.name}_{c.name}_{e}"
        for t in Base.metadata.sorted_tables
        for c in t.columns
        if isinstance(c.type, String) and c.type.length
        for e in ("insert", "update")
    }
    presenti = set(db.execute(text(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'varchar_%'"
    )).scalars())
    # Pavimento: se lo schema non avesse piu' colonne a lunghezza fissa il
    # confronto fra insiemi vuoti passerebbe senza verificare niente.
    assert len(attese) >= 40
    assert attese <= presenti


def test_la_colonna_di_price_alerts_non_accetta_una_direzione_inventata(db: Session) -> None:
    s = _stock(db)
    db.add(PriceAlert(stock_id=s.id, target_price=10.0, direction="crossing_above"))
    with pytest.raises(IntegrityError, match=r"price_alerts\.direction"):
        db.commit()
