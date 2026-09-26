"""Il catalogo del Dow Jones si rinnova di nuovo, e un rinnovo che fallisce si vede (FA-103).

Dal 2026-08-22 il rinnovo del DJI falliva ogni sabato: Wikipedia aveva spostato
i componenti dalla voce dell'indice a «List of Dow Jones Industrial Average
companies», e alla tabella 1 della voce ora ci sono le chiusure annuali. Il
blocco anti-svuotamento ha rifiutato — giustamente — di vuotare l'indice, e
nessun allarme lo ha detto per cinque settimane: sei fallimenti su sei.

Stessa forma del Nasdaq-100 a luglio (vedi la nota in `INDEX_SOURCES`): una
fonte di catalogo puo' morire in silenzio, quindi la correzione e' in due
pezzi — la fonte, e una metrica che conta i fallimenti di fila per indice.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from sqlalchemy.orm import Session

from app.core import app_metrics
from app.models import CatalogRefreshLog, Index, Stock, StockIndex
from app.services.catalog_refresh_service import INDEX_SOURCES, refresh_index

# La forma che rende la pagina elenco, sondata dal pod il 2026-09-26.
DOW = pd.DataFrame({
    "Company": ["3M", "Alphabet (Class A)", "American Express"],
    "Exchange": ["NYSE", "NASDAQ", "NYSE"],
    "Symbol": ["MMM", "GOOGL", "AXP"],
    "Sector": ["Industrials", "Communication Services", "Financials"],
    "Date added": ["1976-08-09", "2026-06-29", "1982-08-30"],
    "Notes": ["As Minnesota Mining and Manufacturing", None, None],
})

# Cio' che la VOCE dell'indice rende oggi alla tabella 1: le chiusure annuali.
CHIUSURE_ANNUALI = pd.DataFrame({
    "Year": [2024, 2025], "Closing value": [42544.22, 48063.29],
    "Net change": [4854.68, 5519.07], "Percentage change": [12.88, 12.97],
})

_SABATO = datetime(2026, 9, 26, 3, 0, tzinfo=UTC)


def _serie(db: Session) -> dict[str, int]:
    return app_metrics.catalog_failure_streaks(db)


def _log(db: Session, codice: str, stato: str, settimane_fa: int) -> None:
    t = _SABATO - timedelta(weeks=settimane_fa)
    db.add(CatalogRefreshLog(index_code=codice, status=stato, started_at=t,
                             completed_at=t + timedelta(minutes=2)))


def _gauge(codice: str) -> float:
    return app_metrics.CATALOG_REFRESH_FAILURE_STREAK.labels(index_code=codice)._value.get()


# ── la fonte ──────────────────────────────────────────────────────────────


def test_la_fonte_del_dow_e_la_pagina_elenco() -> None:
    src = INDEX_SOURCES["DJI"]
    assert str(src["url"]).endswith("/List_of_Dow_Jones_Industrial_Average_companies")
    assert src["table_index"] == 0


def test_il_dow_si_rinnova_dalla_tabella_della_pagina_elenco(db: Session) -> None:
    with patch("app.services.catalog_refresh_service._fetch_table", return_value=DOW):
        r = refresh_index(db, "DJI")
    db.commit()

    assert r.status == "success" and r.stocks_added == 3
    idx = db.query(Index).filter_by(code="DJI").one()
    membri = {
        s.ticker for s in db.query(Stock)
        .join(StockIndex, StockIndex.stock_id == Stock.id)
        .filter(StockIndex.index_id == idx.id)
    }
    assert membri == {"MMM", "GOOGL", "AXP"}
    # La colonna del settore si chiama ora «Sector», non piu' «Industry».
    assert db.query(Stock).filter_by(ticker="AXP").one().sector is not None


def test_la_tabella_sbagliata_nomina_la_causa_non_il_sintomo(db: Session) -> None:
    """«source returned no usable constituents» diceva che la tabella era vuota
    di ticker; la ragione era che non era piu' la tabella dei componenti. Il
    messaggio nuovo nomina la colonna che manca e quelle che ci sono."""
    with patch("app.services.catalog_refresh_service._fetch_table",
               return_value=CHIUSURE_ANNUALI):
        r = refresh_index(db, "DJI")
    db.commit()

    assert r.status == "failed"
    assert "'Symbol'" in (r.error_message or "") and "Year" in (r.error_message or "")


# ── la serie di fallimenti ────────────────────────────────────────────────


def test_la_serie_conta_i_fallimenti_dall_ultimo_rinnovo_riuscito(db: Session) -> None:
    _log(db, "DJI", "failed", 6)
    _log(db, "DJI", "success", 5)
    for settimane in (4, 3, 2, 1, 0):
        _log(db, "DJI", "failed", settimane)
    _log(db, "SP500", "failed", 1)
    _log(db, "SP500", "success", 0)
    db.add(CatalogRefreshLog(index_code="DJI", status="in_progress",
                             started_at=_SABATO + timedelta(hours=1)))
    db.commit()

    serie = _serie(db)
    assert serie["DJI"] == 5          # il rinnovo in corso non e' un esito
    assert serie["SP500"] == 0
    # Un indice senza nessun rinnovo registrato vale zero, non «assente»: una
    # serie che manca non si confronta con niente e la regola tacerebbe.
    assert serie["NDX"] == 0


def test_un_indice_tolto_dalle_fonti_non_resta_in_allarme(db: Session) -> None:
    """SSE 50 e CSI 300 sono stati tolti a mano: i loro fallimenti vecchi non
    devono tenere acceso un allarme che nessun rinnovo potra' mai spegnere."""
    _log(db, "SSE50", "failed", 1)
    _log(db, "SSE50", "failed", 0)
    db.commit()
    assert "SSE50" not in _serie(db)


def test_il_gauge_si_aggiorna_con_la_salute_dei_dati(db: Session) -> None:
    """Gira all'avvio e dopo ogni scansione: un riavvio del pod non azzera la
    serie, perche' si ricalcola dal database."""
    _log(db, "DJI", "failed", 1)
    _log(db, "DJI", "failed", 0)
    db.commit()
    app_metrics.CATALOG_REFRESH_FAILURE_STREAK.labels(index_code="DJI").set(-1)

    app_metrics.refresh_data_health_gauges(db)
    assert _gauge("DJI") == 2


def test_il_job_del_sabato_aggiorna_il_gauge_appena_finito(db: Session, monkeypatch) -> None:
    from app.scheduler.jobs import refresh_catalog

    # ⚠️ Il job importa `SessionLocal` in testa al modulo: la sostituzione del
    # conftest non lo raggiunge, e senza questa riga scriverebbe nel database
    # di sviluppo.
    monkeypatch.setattr(refresh_catalog, "SessionLocal", lambda: db)
    monkeypatch.setattr(refresh_catalog, "refresh_market_caps", lambda _db: None)
    app_metrics.CATALOG_REFRESH_FAILURE_STREAK.labels(index_code="DJI").set(-1)

    with patch("app.services.catalog_refresh_service._fetch_table",
               return_value=CHIUSURE_ANNUALI):
        refresh_catalog.run_refresh_all()
    assert _gauge("DJI") == 1


def test_la_regola_scatta_a_due_sabati_falliti() -> None:
    regole = (Path(__file__).resolve().parents[2] / "infra" / "observability"
              / "app-alert-rules.yaml").read_text(encoding="utf-8")
    assert "- alert: FinanceAlertCatalogRefreshFailing" in regole
    assert "finance_alert_catalog_refresh_failure_streak >= 2" in regole
