"""Semina i quindici titoli asiatici negoziabili in dollari, e SOLO quelli.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.seed_asia_adr

Perche' esiste uno script invece di un `python -m app.scripts.seed`
=================================================================
Il seme e' idempotente per RIGA, ma `seed.py` lavora per FILE — e dal 2026-06
le due cose non coincidono piu'. La potatura (1494 -> 1000 titoli) ha cancellato
righe dal DB senza toccare i CSV, quindi oggi, misurato in produzione:

    direxion_etfs.csv    36 righe dichiarate,  10 vive,  26 tolte
    catalog_extras.csv  197 righe dichiarate, 112 vive,  85 tolte

Una risemina canonica riporterebbe dentro 111 righe che qualcuno aveva tolto di
proposito: universo 1010 -> ~1121 e un +11% di costo di scansione, in silenzio.
Questo script e' ristretto alle righe.

Cosa semina
===========
1. `asia_adr.csv` per intero — 14 ADR su NYSE/NASDAQ, verificati contro
   yfinance il 2026-09-17 prima di essere scritti: 252 barre a testa, ultima
   barra del giorno, valuta USD, ZERO barre a volume nullo.

   ⚠️ La verifica non e' una formalita'. Nello stesso giro `CAJ` (ADR Canon)
   e' risultato senza dati — l'ADR non e' piu' quotato — e sarebbe entrato in
   catalogo per finire in quarantena dopo tre tentativi a vuoto.

2. Da `direxion_etfs.csv`, SOLO i ticker in `SOLO_DA_DIREXION`. YINN e' gia'
   dichiarata li' con la forma giusta (`industry=Leveraged ETF`, che
   `is_fund_industry` traduce in `instrument_type="etf"`), e una seconda
   dichiarazione in `asia_adr.csv` sarebbe una copia che diverge appena
   qualcuno ne tocca una. Un proprietario solo, e il filtro qui.

Cosa NON semina, e perche'
==========================
Samsung (005930.KS) e SK Hynix (000660.KS) NON sono qui: sono in catalogo dal
primo seed, dentro `kospi20.csv`, con 2538 barre a testa. Non erano assenti,
erano INVISIBILI — stanno su KRX, che `app/core/visibility.py` tiene
breadth-only. Le rende visibili `SURFACED_TICKERS`, non una riga nuova.

E non esistono loro ADR americani: misurato il 2026-09-17, `SSNLF` (Samsung
OTC) risponde con 127 barre su 127 a VOLUME ZERO — cioe' prezzi riportati e mai
osservati, la firma esatta del difetto che `repair_bar_quality` esiste per
togliere — mentre `HXSCL`/`HXSCF` (SK Hynix OTC) non rispondono affatto.

Una nota sui commenti
=====================
⚠️ Le motivazioni stanno QUI e non nei CSV: `csv.DictReader` non conosce i
commenti, quindi una riga che comincia con '#' diventerebbe una riga di dati
con `name` vuoto, e `Stock.name` e' NOT NULL.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.services.seed_service import SeedResult, seed_stocks_subset_from_csv

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"

ASIA_CSV = "asia_adr.csv"
DIREXION_CSV = "direxion_etfs.csv"

#: Le uniche righe che questo script prende da `direxion_etfs.csv`. ⚠️ NON
#: allargarlo per comodita': ogni ticker aggiunto qui e' un prodotto a leva che
#: la potatura aveva tolto. YANG — lo speculare ribassista di YINN — e' fuori
#: perche' non e' stato chiesto, non perche' sia stato dimenticato.
SOLO_DA_DIREXION: frozenset[str] = frozenset({"YINN"})


def semina(db: Session) -> SeedResult:
    """Upsert delle righe volute. Idempotente: una seconda corsa aggiorna e
    basta. Non fa commit — lo decide il chiamante (i test non committano)."""
    totale = SeedResult(added=0, updated=0)
    for filename, only in ((ASIA_CSV, None), (DIREXION_CSV, SOLO_DA_DIREXION)):
        path = SEED_DIR / filename
        if not path.exists():
            logger.warning(f"Seed file mancante: {path}")
            continue
        with path.open(encoding="utf-8") as f:
            res = seed_stocks_subset_from_csv(db, f, only=only)
        quali = "tutte" if only is None else ", ".join(sorted(only))
        logger.info(f"{filename} ({quali}): added={res.added} updated={res.updated}")
        totale = SeedResult(added=totale.added + res.added,
                            updated=totale.updated + res.updated)
    return totale


def run() -> None:
    db = SessionLocal()
    try:
        res = semina(db)
        db.commit()
        logger.info(f"Totale: added={res.added} updated={res.updated}")
        logger.info(
            "Lo storico arriva da se': una riga con zero barre entra nel gruppo "
            "`backfill` di ohlcv_fetch_plan e paga il download 10y alla prossima "
            "scansione. Nessun comando manuale."
        )
    finally:
        db.close()


if __name__ == "__main__":
    run()
