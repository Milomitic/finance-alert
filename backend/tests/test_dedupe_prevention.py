"""Test di *prevenzione*: scenari concreti che, in passato, generavano
righe duplicate nella tabella `stocks`. Devono ora fallire silenziosamente
nel creare il duplicato — l'unicità del ticker è invariante post-pulizia.

Casi coperti:
1. `seed_service` riceve CSV legacy con label leggibili ("Borsa Italiana")
   e scrive comunque il codice canonico ("BIT") → no duplicato col catalog.
2. Re-eseguire il `seed` non duplica.
3. `catalog_refresh_service` per ticker US senza suffisso noto già
   presente in un altro indice (default_exchange diverso) riusa la riga
   esistente invece di crearne una nuova.
4. `has_known_suffix` / `canonical_exchange` esposti dal modulo condiviso
   restituiscono valori coerenti con la mappa storica.
"""
from __future__ import annotations

import io
from unittest.mock import patch

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Stock
from app.services.catalog_refresh_service import refresh_index
from app.services.exchange_codes import (
    SUFFIX_TO_EXCHANGE,
    canonical_exchange,
    has_known_suffix,
)
from app.services.seed_service import seed_index_from_csv

# --- helpers --------------------------------------------------------------

LEGACY_CSV = """ticker,name,exchange,sector,industry,country,currency
ENEL.MI,Enel S.p.A.,Borsa Italiana,Utilities,Electric Utilities,IT,EUR
ASML.AS,ASML Holding NV,Euronext Amsterdam,Technology,Semiconductors,NL,EUR
BNP.PA,BNP Paribas,Euronext Paris,Financials,Banks,FR,EUR
"""

CANONICAL_CSV = """ticker,name,exchange,sector,industry,country,currency
ENEL.MI,Enel S.p.A.,BIT,Utilities,Electric Utilities,IT,EUR
ASML.AS,ASML Holding NV,AEX,Technology,Semiconductors,NL,EUR
BNP.PA,BNP Paribas,EPA,Financials,Banks,FR,EUR
"""

SP500_TABLE = pd.DataFrame({
    "Symbol": ["AAPL"],
    "Security": ["Apple Inc."],
    "GICS Sector": ["Technology"],
    "GICS Sub-Industry": ["Hardware"],
})

DJI_TABLE = pd.DataFrame({
    "Symbol": ["AAPL"],
    "Company": ["Apple"],
    "Industry": ["Technology"],
})


# --- (1) seed_service canonicalizza CSV legacy ----------------------------

def test_seed_canonicalizes_legacy_human_readable_exchange(db: Session) -> None:
    """CSV vecchio stile ("Borsa Italiana") deve atterrare in DB come "BIT"."""
    seed_index_from_csv(
        db, io.StringIO(LEGACY_CSV),
        index_code="FTSEMIB", index_name="FTSE MIB", country="IT",
    )
    db.commit()

    rows = {s.ticker: s.exchange for s in db.query(Stock).all()}
    assert rows == {"ENEL.MI": "BIT", "ASML.AS": "AEX", "BNP.PA": "EPA"}


def test_seed_legacy_then_canonical_csv_does_not_duplicate(db: Session) -> None:
    """Riimportare lo stesso indice con il CSV "moderno" trova le righe
    esistenti (perché entrambi i CSV scrivono "BIT", "AEX", "EPA") e non
    duplica nulla."""
    seed_index_from_csv(
        db, io.StringIO(LEGACY_CSV),
        index_code="FTSEMIB", index_name="FTSE MIB", country="IT",
    )
    db.commit()
    result = seed_index_from_csv(
        db, io.StringIO(CANONICAL_CSV),
        index_code="FTSEMIB", index_name="FTSE MIB", country="IT",
    )
    db.commit()

    assert result.added == 0
    assert result.updated == 3
    assert db.query(Stock).count() == 3
    # Nessun ticker compare due volte:
    tickers = [s.ticker for s in db.query(Stock).all()]
    assert sorted(tickers) == sorted(set(tickers))


# --- (2) re-seed idempotente già coperto da test_seed_service ma -----------
#         lo verifichiamo anche con il nostro CSV legacy ---------------------

def test_seed_legacy_csv_is_idempotent(db: Session) -> None:
    seed_index_from_csv(
        db, io.StringIO(LEGACY_CSV),
        index_code="FTSEMIB", index_name="FTSE MIB", country="IT",
    )
    db.commit()
    result = seed_index_from_csv(
        db, io.StringIO(LEGACY_CSV),
        index_code="FTSEMIB", index_name="FTSE MIB", country="IT",
    )
    db.commit()

    assert result.added == 0
    assert result.updated == 3
    assert db.query(Stock).count() == 3


# --- (3) catalog_refresh non duplica ticker US cross-index ----------------

def test_catalog_refresh_us_ticker_in_two_indices_does_not_duplicate(
    db: Session,
) -> None:
    """AAPL appare in SP500 (default=NASDAQ) e in DJI (default=NYSE).
    Storicamente questo creava due righe `AAPL`. Ora la seconda refresh
    deve riusare la riga esistente."""
    with patch(
        "app.services.catalog_refresh_service._fetch_table",
        return_value=SP500_TABLE,
    ):
        refresh_index(db, "SP500")
    with patch(
        "app.services.catalog_refresh_service._fetch_table",
        return_value=DJI_TABLE,
    ):
        refresh_index(db, "DJI")
    db.commit()

    rows = db.query(Stock).filter_by(ticker="AAPL").all()
    assert len(rows) == 1, f"Expected 1 AAPL row, got {len(rows)}: {[(r.id, r.exchange) for r in rows]}"
    # Il primo refresh ha vinto (NASDAQ), il secondo refresh ha aggiornato
    # i campi (name -> "Apple") ma NON l'exchange (che resta autoritativo
    # per la prima ingestion).
    assert rows[0].exchange == "NASDAQ"


def test_catalog_refresh_european_ticker_unaffected(db: Session) -> None:
    """Sanity: il fix per i ticker US non degrada il caso europeo
    (suffisso noto)."""
    ftsemib_table = pd.DataFrame({
        "Ticker": ["ENEL.MI", "ENI.MI"],
        "Company": ["Enel", "Eni"],
        "ICB Sector": ["Utilities", "Energy"],
    })
    with patch(
        "app.services.catalog_refresh_service._fetch_table",
        return_value=ftsemib_table,
    ):
        refresh_index(db, "FTSEMIB")
    db.commit()

    rows = {s.ticker: s.exchange for s in db.query(Stock).all()}
    assert rows == {"ENEL.MI": "BIT", "ENI.MI": "BIT"}


# --- (4) helper del modulo condiviso --------------------------------------

def test_canonical_exchange_known_suffixes() -> None:
    assert canonical_exchange("ENEL.MI", "Borsa Italiana") == "BIT"
    assert canonical_exchange("ASML.AS", "Euronext Amsterdam") == "AEX"
    assert canonical_exchange("BNP.PA", "anything") == "EPA"
    assert canonical_exchange("0700.HK", "anything") == "HKEX"


def test_canonical_exchange_unknown_suffix_keeps_default() -> None:
    assert canonical_exchange("AAPL", "NASDAQ") == "NASDAQ"
    assert canonical_exchange("AAPL", "NYSE") == "NYSE"
    assert canonical_exchange("MSFT", "X") == "X"


def test_canonical_exchange_is_case_insensitive_on_input() -> None:
    """Anche se il CSV passa il ticker in lowercase, il match suffix funziona."""
    assert canonical_exchange("enel.mi", "X") == "BIT"


def test_has_known_suffix_truth_table() -> None:
    assert has_known_suffix("ENEL.MI") is True
    assert has_known_suffix("ASML.AS") is True
    assert has_known_suffix("0700.HK") is True
    assert has_known_suffix("AAPL") is False
    assert has_known_suffix("BRK.B") is False  # ".B" non è un exchange suffix


def test_suffix_map_covers_all_european_seed_files() -> None:
    """Smoke: tutti i suffissi yfinance attesi sono mappati. Se qualcuno
    aggiunge un nuovo mercato (es. .TO per Toronto) e dimentica di
    estendere `SUFFIX_TO_EXCHANGE`, questo test resta verde — è solo
    una sentinella sui valori già noti, non sull'esaustività futura."""
    expected_subset = {".MI", ".AS", ".PA", ".DE", ".HK", ".SS", ".SZ", ".L"}
    assert expected_subset <= set(SUFFIX_TO_EXCHANGE)
