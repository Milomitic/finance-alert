"""app.scripts.backfill_13f_history — fixture-driven, zero network.

All EDGAR endpoints (submissions JSON, filing index.json, infotable XML,
company_tickers.json) are served from in-memory fixtures by patching the
scraper's `_http_get_json` / `_http_get_text` seams. The autouse
anti-network guard in conftest guarantees any un-mocked call explodes.

Scenario (one curated fund, 3 quarters):
    Q3'25 (oldest): AAPL 100sh, MSFT 50sh
    Q4'25:          AAPL 150sh (+50% add), MSFT gone (sold_out), NVDA 10sh (new)
    Q1'26 (latest): AAPL 150sh (hold), NVDA 20sh (+100% add)
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.models import (
    Institutional,
    InstitutionalFiling,
    InstitutionalHolding,
    Stock,
)
from app.scripts.backfill_13f_history import run_backfill
from app.services import sec_13f_scraper

FUND = sec_13f_scraper.CuratedFund(
    999, "sec-testfund", "Test Fund", "Test Manager", "hedge_fund"
)

_NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def _row(issuer: str, cusip: str, value: int, shares: int) -> str:
    return (
        "<infoTable>"
        f"<nameOfIssuer>{issuer}</nameOfIssuer>"
        f"<cusip>{cusip}</cusip>"
        f"<value>{value}</value>"
        "<shrsOrPrnAmt>"
        f"<sshPrnamt>{shares}</sshPrnamt>"
        "<sshPrnamtType>SH</sshPrnamtType>"
        "</shrsOrPrnAmt>"
        "</infoTable>"
    )


def _xml(rows: str) -> str:
    return f'<informationTable xmlns="{_NS}">{rows}</informationTable>'


# EDGAR lists filings NEWEST-FIRST; accession numbers dash-formatted.
SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["13F-HR", "10-K", "13F-HR", "13F-HR"],
            "accessionNumber": [
                "0000000000-26-000003",
                "0000000000-26-000090",
                "0000000000-26-000002",
                "0000000000-25-000001",
            ],
            "reportDate": ["2026-03-31", "2025-12-31", "2025-12-31", "2025-09-30"],
            "filingDate": ["2026-05-14", "2026-02-01", "2026-02-13", "2025-11-14"],
        }
    }
}

INFO_TABLES = {
    # Q3'25 — oldest
    "000000000025000001": _xml(
        _row("APPLE INC", "037833100", 10_000, 100)
        + _row("MICROSOFT CORP", "594918104", 5_000, 50)
    ),
    # Q4'25
    "000000000026000002": _xml(
        _row("APPLE INC", "037833100", 15_000, 150)
        + _row("NVIDIA CORP", "67066G104", 1_000, 10)
    ),
    # Q1'26 — latest
    "000000000026000003": _xml(
        _row("APPLE INC", "037833100", 15_000, 150)
        + _row("NVIDIA CORP", "67066G104", 2_000, 20)
    ),
}

COMPANY_TICKERS = {
    "0": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "Nvidia Corp"},
}

INDEX_JSON = {
    "directory": {
        "item": [
            {"name": "primary_doc.xml", "size": "1000"},
            {"name": "infotable.xml", "size": "50000"},
        ]
    }
}


@pytest.fixture
def edgar_fixtures(monkeypatch):
    """Patch the scraper's HTTP seams to serve the fixture EDGAR."""

    def fake_json(url: str):
        if "company_tickers.json" in url:
            return COMPANY_TICKERS
        if "data.sec.gov/submissions/" in url:
            return SUBMISSIONS
        if url.endswith("/index.json"):
            return INDEX_JSON
        raise AssertionError(f"unexpected JSON fetch: {url}")

    def fake_text(url: str):
        # .../edgar/data/{cik}/{acc_clean}/infotable.xml
        acc_clean = url.rstrip("/").split("/")[-2]
        xml = INFO_TABLES.get(acc_clean)
        if xml is None:
            raise AssertionError(f"unexpected XML fetch: {url}")
        return xml

    monkeypatch.setattr(sec_13f_scraper, "_http_get_json", fake_json)
    monkeypatch.setattr(sec_13f_scraper, "_http_get_text", fake_text)
    monkeypatch.setattr(sec_13f_scraper, "_POLITE_DELAY_SEC", 0)


@pytest.fixture
def catalog(db):
    """AAPL in catalog (pass 1); MSFT/NVDA only in company_tickers (pass 2)."""
    db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc."))
    db.flush()
    return db


def _filings(db, slug="sec-testfund"):
    inst = db.execute(
        select(Institutional).where(Institutional.slug == slug)
    ).scalar_one()
    return inst, sorted(
        db.execute(
            select(InstitutionalFiling).where(
                InstitutionalFiling.institutional_id == inst.id
            )
        ).scalars(),
        key=lambda f: f.period_end_date,
    )


def _holdings_by_ticker(db, filing_id):
    return {
        h.ticker: h
        for h in db.execute(
            select(InstitutionalHolding).where(
                InstitutionalHolding.filing_id == filing_id
            )
        ).scalars()
    }


class TestFetchHistoryOrdering:
    def test_oldest_first_with_filed_dates(self, edgar_fixtures):
        filings = sec_13f_scraper.fetch_13f_history(FUND, quarters=5)
        assert [f.period_end_date for f in filings] == [
            date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31),
        ]
        assert [f.filed_date for f in filings] == [
            date(2025, 11, 14), date(2026, 2, 13), date(2026, 5, 14),
        ]

    def test_quarters_takes_the_most_recent_n(self, edgar_fixtures):
        filings = sec_13f_scraper.fetch_13f_history(FUND, quarters=2)
        # Last 2 quarters, still oldest-first.
        assert [f.period_end_date for f in filings] == [
            date(2025, 12, 31), date(2026, 3, 31),
        ]


class TestBackfillRun:
    def test_ingests_history_and_chains_qoq(self, edgar_fixtures, catalog):
        db = catalog
        summary = run_backfill(db, [FUND], quarters=5)
        assert summary.funds_processed == 1
        assert summary.filings_ingested == 3

        inst, filings = _filings(db)
        assert [f.period_end_date for f in filings] == [
            date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31),
        ]
        # filed_date threaded on every filing row.
        assert [f.filed_date for f in filings] == [
            date(2025, 11, 14), date(2026, 2, 13), date(2026, 5, 14),
        ]

        # Q3'25 (oldest — no baseline): actions must be None, never "new".
        q3 = _holdings_by_ticker(db, filings[0].id)
        assert set(q3) == {"AAPL", "MSFT"}
        assert all(h.action is None for h in q3.values())

        # Q4'25: AAPL +50% add, NVDA new, MSFT sold_out phantom row.
        q4 = _holdings_by_ticker(db, filings[1].id)
        assert q4["AAPL"].action == "add"
        assert q4["AAPL"].qoq_change_pct == pytest.approx(50.0)
        assert q4["AAPL"].qoq_change_shares == 50
        assert q4["NVDA"].action == "new"
        assert q4["MSFT"].action == "sold_out"
        assert q4["MSFT"].shares == 0
        assert q4["MSFT"].qoq_change_pct == pytest.approx(-100.0)

        # Q1'26: AAPL flat → hold, NVDA doubled → add.
        q1 = _holdings_by_ticker(db, filings[2].id)
        assert q1["AAPL"].action == "hold"
        assert q1["NVDA"].action == "add"
        assert q1["NVDA"].qoq_change_pct == pytest.approx(100.0)

    def test_resolution_uses_all_three_passes(self, edgar_fixtures, catalog):
        db = catalog
        summary = run_backfill(db, [FUND], quarters=5)
        # Q3'25: AAPL via catalog, MSFT via SEC map (2 new resolutions);
        # later filings short-circuit on the in-run cusip_map (pass 0).
        assert summary.resolution.from_catalog >= 1
        assert summary.resolution.from_sec >= 1
        assert summary.resolution.from_map >= 1
        assert summary.resolution.unresolved == 0
        assert sec_13f_scraper.load_cusip_ticker_map(db) == {
            "037833100": "AAPL",
            "594918104": "MSFT",
            "67066G104": "NVDA",
        }

    def test_idempotent_rerun(self, edgar_fixtures, catalog):
        db = catalog
        run_backfill(db, [FUND], quarters=5)
        first = {
            f.id: len(_holdings_by_ticker(db, f.id))
            for f in _filings(db)[1]
        }
        summary2 = run_backfill(db, [FUND], quarters=5)
        assert summary2.filings_ingested == 3

        inst, filings = _filings(db)
        assert len(filings) == 3  # upsert by period — no duplicate filings
        second = {f.id: len(_holdings_by_ticker(db, f.id)) for f in filings}
        assert second == first  # wipe + re-insert → stable row counts
        # Q/Q labels survive the recompute identically.
        q4 = _holdings_by_ticker(db, filings[1].id)
        assert q4["AAPL"].action == "add"
        assert q4["MSFT"].action == "sold_out"
        # Second run resolves everything from the persisted map (pass 0):
        # 2 CUSIP rows per filing × 3 filings = 6 short-circuit hits.
        assert summary2.resolution.from_catalog == 0
        assert summary2.resolution.from_sec == 0
        assert summary2.resolution.from_map == 6

    def test_dry_run_rolls_everything_back(self, edgar_fixtures, catalog):
        db = catalog
        summary = run_backfill(db, [FUND], quarters=5, dry_run=True)
        assert summary.filings_ingested == 3  # work happened...
        # ...but nothing persisted: no institutional, no filings, no map rows.
        assert db.execute(select(Institutional)).scalars().all() == []
        assert db.execute(select(InstitutionalFiling)).scalars().all() == []
        assert sec_13f_scraper.load_cusip_ticker_map(db) == {}

    def test_fund_with_no_filings_is_skipped(self, catalog, monkeypatch):
        db = catalog
        monkeypatch.setattr(
            sec_13f_scraper, "_http_get_json",
            lambda url: {} if "company_tickers" in url else None,
        )
        summary = run_backfill(db, [FUND], quarters=5)
        assert summary.funds_skipped == 1
        assert summary.funds_processed == 0
        assert db.execute(select(InstitutionalFiling)).scalars().all() == []
