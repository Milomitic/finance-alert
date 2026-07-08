"""SEC 13F scraper: put/call skip, CUSIP three-pass resolution, filed_date.

No network anywhere: parsing tests feed XML strings straight into the
parser; resolution tests build the maps by hand or monkeypatch the
module-level `_http_get_json` seam (below the anti-network guard, so a
forgotten mock fails loudly).
"""
from datetime import date

from sqlalchemy import select

from app.models import CusipTickerMap, InstitutionalFiling, Stock
from app.services import institutional_service, sec_13f_scraper
from app.services.institutional_scraper import ScrapedFiling, ScrapedManager

_NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def _info_table_xml(rows: str) -> str:
    return f'<informationTable xmlns="{_NS}">{rows}</informationTable>'


def _row(
    issuer: str,
    cusip: str,
    value: int,
    shares: int,
    ssh_type: str = "SH",
    put_call: str | None = None,
) -> str:
    pc = f"<putCall>{put_call}</putCall>" if put_call else ""
    return (
        "<infoTable>"
        f"<nameOfIssuer>{issuer}</nameOfIssuer>"
        f"<cusip>{cusip}</cusip>"
        f"<value>{value}</value>"
        "<shrsOrPrnAmt>"
        f"<sshPrnamt>{shares}</sshPrnamt>"
        f"<sshPrnamtType>{ssh_type}</sshPrnamtType>"
        "</shrsOrPrnAmt>"
        f"{pc}"
        "</infoTable>"
    )


# ---------------------------------------------------------------------------
# 1. Put/Call rows must be skipped (they were summed as long stock)
# ---------------------------------------------------------------------------

class TestPutCallSkip:
    def test_put_and_call_rows_are_skipped(self):
        xml = _info_table_xml(
            _row("APPLE INC", "037833100", 1_000_000, 5000)
            + _row("NVIDIA CORP", "67066G104", 500_000, 2000, put_call="Put")
            + _row("NVIDIA CORP", "67066G104", 300_000, 1000, put_call="Call")
            + _row("MICROSOFT CORP", "594918104", 700_000, 3000)
        )
        holdings = list(sec_13f_scraper._parse_info_table(xml))
        assert len(holdings) == 2
        tickers = {h.ticker for h in holdings}
        assert tickers == {"CUSIP:037833100", "CUSIP:594918104"}
        # The option rows' value must NOT leak into any surviving row.
        assert sum(h.value_usd for h in holdings) == 1_700_000

    def test_putcall_value_is_case_insensitive(self):
        xml = _info_table_xml(
            _row("NVIDIA CORP", "67066G104", 500_000, 2000, put_call="PUT")
            + _row("NVIDIA CORP", "67066G104", 100_000, 400, put_call="call")
        )
        assert list(sec_13f_scraper._parse_info_table(xml)) == []

    def test_plain_sh_row_without_putcall_element_survives(self):
        xml = _info_table_xml(_row("APPLE INC", "037833100", 42, 7))
        holdings = list(sec_13f_scraper._parse_info_table(xml))
        assert len(holdings) == 1
        assert holdings[0].shares == 7

    def test_option_shares_excluded_from_cusip_aggregation(self):
        # Same CUSIP, one SH + one Put row: the aggregate must only see
        # the SH leg (the historical bug summed both as long stock).
        xml = _info_table_xml(
            _row("NVIDIA CORP", "67066G104", 500_000, 2000)
            + _row("NVIDIA CORP", "67066G104", 900_000, 9000, put_call="Put")
        )
        holdings = sec_13f_scraper._aggregate_by_cusip(
            list(sec_13f_scraper._parse_info_table(xml))
        )
        assert len(holdings) == 1
        assert holdings[0].shares == 2000
        assert holdings[0].value_usd == 500_000


# ---------------------------------------------------------------------------
# 2. Issuer-name normalization (shared by catalog + SEC passes)
# ---------------------------------------------------------------------------

class TestNormalizeIssuerName:
    def test_strips_corporate_suffixes(self):
        assert sec_13f_scraper.normalize_issuer_name("Apple Inc.") == "APPLE"
        assert sec_13f_scraper.normalize_issuer_name("APPLE INC") == "APPLE"
        assert (
            sec_13f_scraper.normalize_issuer_name("MICROSOFT CORP")
            == "MICROSOFT"
        )

    def test_strips_share_class_decorations(self):
        # "CL A" / "CLASS C" / trailing letters after suffix stripping
        assert sec_13f_scraper.normalize_issuer_name("ALPHABET INC CL C") == "ALPHABET"
        assert (
            sec_13f_scraper.normalize_issuer_name("ALPHABET INC CLASS A")
            == "ALPHABET"
        )
        assert (
            sec_13f_scraper.normalize_issuer_name("BERKSHIRE HATHAWAY INC DEL CL B")
            == "BERKSHIRE HATHAWAY"
        )

    def test_does_not_strip_single_letter_only_name(self):
        # A ticker-like one-letter issuer must not collapse to "".
        assert sec_13f_scraper.normalize_issuer_name("X CORP") == "X"


# ---------------------------------------------------------------------------
# 3. company_tickers.json fetch → normalized-title map
# ---------------------------------------------------------------------------

class TestFetchSecCompanyTickers:
    def test_builds_normalized_map_first_write_wins(self, monkeypatch):
        payload = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            # GOOGL comes before GOOG in the mkt-cap-ordered file: on the
            # normalized-title collision the primary listing must win.
            "1": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
            "2": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
        }
        monkeypatch.setattr(
            sec_13f_scraper, "_http_get_json", lambda url: payload
        )
        out = sec_13f_scraper.fetch_sec_company_tickers()
        assert out == {"APPLE": "AAPL", "ALPHABET": "GOOGL"}

    def test_fetch_failure_returns_empty_map(self, monkeypatch):
        monkeypatch.setattr(sec_13f_scraper, "_http_get_json", lambda url: None)
        assert sec_13f_scraper.fetch_sec_company_tickers() == {}


# ---------------------------------------------------------------------------
# 4. Three-pass resolution
# ---------------------------------------------------------------------------

def _filing_with(*holdings) -> ScrapedFiling:
    return ScrapedFiling(
        code="sec-test",
        period_end_date=date(2026, 3, 31),
        total_value_usd=None,
        holdings=list(holdings),
    )


def _cusip_holding(cusip: str, issuer: str, shares=100, value=1000):
    xml = _info_table_xml(_row(issuer, cusip, value, shares))
    return list(sec_13f_scraper._parse_info_table(xml))[0]


class TestResolveFilingHoldings:
    def test_map_first_short_circuit(self):
        # Pass 0 hit: the persisted map wins even when catalog/SEC maps
        # would give a different answer — and produces NO new resolution.
        h = _cusip_holding("037833100", "APPLE INC")
        filing = _filing_with(h)
        stats, new_res = sec_13f_scraper.resolve_filing_holdings(
            filing,
            cusip_map={"037833100": "AAPL"},
            catalog_map={"APPLE": "WRONG"},
            sec_map={"APPLE": "WRONG2"},
        )
        assert filing.holdings[0].ticker == "AAPL"
        assert stats.from_map == 1
        assert stats.from_catalog == stats.from_sec == stats.unresolved == 0
        assert new_res == {}

    def test_catalog_pass_records_new_resolution(self):
        h = _cusip_holding("037833100", "APPLE INC")
        filing = _filing_with(h)
        cusip_map: dict[str, str] = {}
        stats, new_res = sec_13f_scraper.resolve_filing_holdings(
            filing, cusip_map=cusip_map, catalog_map={"APPLE": "AAPL"},
        )
        assert filing.holdings[0].ticker == "AAPL"
        assert stats.from_catalog == 1
        assert new_res == {"037833100": ("AAPL", "catalog", "APPLE INC")}
        # In-run cumulativity: the shared cusip_map learned the hit.
        assert cusip_map["037833100"] == "AAPL"

    def test_sec_pass_resolves_what_catalog_misses(self):
        h = _cusip_holding("67066G104", "NVIDIA CORP")
        filing = _filing_with(h)
        stats, new_res = sec_13f_scraper.resolve_filing_holdings(
            filing,
            cusip_map={},
            catalog_map={},  # catalog misses it
            sec_map={"NVIDIA": "NVDA"},
        )
        assert filing.holdings[0].ticker == "NVDA"
        assert stats.from_sec == 1
        assert new_res == {"67066G104": ("NVDA", "sec_company_tickers", "NVIDIA CORP")}

    def test_unresolved_keeps_cusip_placeholder(self):
        h = _cusip_holding("999999999", "OBSCURE MICROCAP LLC")
        filing = _filing_with(h)
        stats, new_res = sec_13f_scraper.resolve_filing_holdings(
            filing, cusip_map={}, catalog_map={}, sec_map={},
        )
        assert filing.holdings[0].ticker == "CUSIP:999999999"
        assert stats.unresolved == 1
        assert new_res == {}

    def test_share_classes_merging_to_same_ticker(self):
        # Two CUSIPs (Alphabet A + C) normalize to the same stem and
        # resolve to the same ticker → merged into ONE holding so the
        # UNIQUE(filing_id, ticker) constraint holds at persistence.
        a = _cusip_holding("02079K305", "ALPHABET INC CL A", shares=10, value=100)
        c = _cusip_holding("02079K107", "ALPHABET INC CL C", shares=5, value=50)
        filing = _filing_with(a, c)
        stats, new_res = sec_13f_scraper.resolve_filing_holdings(
            filing, cusip_map={}, catalog_map={"ALPHABET": "GOOGL"},
        )
        assert len(filing.holdings) == 1
        merged = filing.holdings[0]
        assert merged.ticker == "GOOGL"
        assert merged.shares == 15
        assert merged.value_usd == 150
        # Both CUSIPs still individually persisted for future pass-0 hits.
        assert set(new_res) == {"02079K305", "02079K107"}


# ---------------------------------------------------------------------------
# 5. cusip_ticker_map persistence (cumulative across runs)
# ---------------------------------------------------------------------------

class TestCusipMapPersistence:
    def test_persist_then_load_roundtrip(self, db):
        n = sec_13f_scraper.persist_cusip_resolutions(
            db,
            {
                "037833100": ("AAPL", "catalog", "APPLE INC"),
                "67066G104": ("NVDA", "sec_company_tickers", "NVIDIA CORP"),
            },
        )
        assert n == 2
        loaded = sec_13f_scraper.load_cusip_ticker_map(db)
        assert loaded == {"037833100": "AAPL", "67066G104": "NVDA"}
        row = db.get(CusipTickerMap, "67066G104")
        assert row.source == "sec_company_tickers"
        assert row.issuer_name == "NVIDIA CORP"

    def test_re_persist_updates_instead_of_duplicating(self, db):
        sec_13f_scraper.persist_cusip_resolutions(
            db, {"037833100": ("AAPL", "catalog", "APPLE INC")}
        )
        sec_13f_scraper.persist_cusip_resolutions(
            db, {"037833100": ("AAPL", "sec_company_tickers", "APPLE INC")}
        )
        rows = db.execute(select(CusipTickerMap)).scalars().all()
        assert len(rows) == 1
        assert rows[0].source == "sec_company_tickers"

    def test_loaded_map_short_circuits_next_run(self, db):
        """End-to-end cumulativity: run 1 resolves via catalog and
        persists; run 2 (fresh maps, empty catalog) resolves via pass 0."""
        filing1 = _filing_with(_cusip_holding("037833100", "APPLE INC"))
        cusip_map = sec_13f_scraper.load_cusip_ticker_map(db)
        _, new_res = sec_13f_scraper.resolve_filing_holdings(
            filing1, cusip_map=cusip_map, catalog_map={"APPLE": "AAPL"},
        )
        sec_13f_scraper.persist_cusip_resolutions(db, new_res)

        # "Next run": reload from DB, catalog no longer matches.
        filing2 = _filing_with(_cusip_holding("037833100", "APPLE INC"))
        stats, new_res2 = sec_13f_scraper.resolve_filing_holdings(
            filing2,
            cusip_map=sec_13f_scraper.load_cusip_ticker_map(db),
            catalog_map={},
            sec_map={},
        )
        assert filing2.holdings[0].ticker == "AAPL"
        assert stats.from_map == 1
        assert new_res2 == {}


# ---------------------------------------------------------------------------
# 6. filed_date threading (ScrapedFiling → upsert_filing)
# ---------------------------------------------------------------------------

def _make_inst(db, slug="sec-testfund", source="sec_13f"):
    manager = ScrapedManager(code="999", slug=slug, name="Test Fund")
    inst, _ = institutional_service.upsert_institutional(
        db, manager, type_="hedge_fund", source=source
    )
    return inst


class TestFiledDateThreading:
    def test_sec_path_writes_filed_date(self, db):
        inst = _make_inst(db)
        filing = ScrapedFiling(
            code="sec-testfund",
            period_end_date=date(2026, 3, 31),
            total_value_usd=1_000,
            filed_date=date(2026, 5, 14),
        )
        row, created = institutional_service.upsert_filing(db, inst, filing)
        assert created is True
        assert row.filed_date == date(2026, 5, 14)

    def test_dataroma_path_leaves_filed_date_null(self, db):
        inst = _make_inst(db, slug="brk", source="dataroma")
        # Dataroma's scraper never sets filed_date — the DTO default (None)
        # must persist as NULL.
        filing = ScrapedFiling(
            code="brk",
            period_end_date=date(2026, 3, 31),
            total_value_usd=1_000,
        )
        row, _ = institutional_service.upsert_filing(db, inst, filing)
        assert row.filed_date is None

    def test_replace_updates_filed_date_but_never_nulls_it(self, db):
        inst = _make_inst(db)
        first = ScrapedFiling(
            code="sec-testfund",
            period_end_date=date(2026, 3, 31),
            total_value_usd=1_000,
            filed_date=date(2026, 5, 14),
        )
        institutional_service.upsert_filing(db, inst, first)
        # Re-publish with a corrected filed_date → updated in place.
        corrected = ScrapedFiling(
            code="sec-testfund",
            period_end_date=date(2026, 3, 31),
            total_value_usd=1_100,
            filed_date=date(2026, 5, 15),
        )
        row, created = institutional_service.upsert_filing(db, inst, corrected)
        assert created is False
        assert row.filed_date == date(2026, 5, 15)
        # A later pass WITHOUT a filed_date must not clobber the known one.
        undated = ScrapedFiling(
            code="sec-testfund",
            period_end_date=date(2026, 3, 31),
            total_value_usd=1_200,
        )
        row2, _ = institutional_service.upsert_filing(db, inst, undated)
        assert row2.filed_date == date(2026, 5, 15)

    def test_fetch_latest_13f_populates_filed_date(self, monkeypatch):
        """The SEC scrape path threads EDGAR's filingDate into the DTO."""
        fund = sec_13f_scraper.CuratedFund(
            999, "sec-testfund", "Test Fund", None, "hedge_fund"
        )
        submissions = {
            "filings": {
                "recent": {
                    "form": ["13F-HR"],
                    "accessionNumber": ["0000000000-26-000001"],
                    "reportDate": ["2026-03-31"],
                    "filingDate": ["2026-05-14"],
                }
            }
        }
        index = {
            "directory": {
                "item": [
                    {"name": "primary_doc.xml", "size": "1000"},
                    {"name": "infotable.xml", "size": "50000"},
                ]
            }
        }

        def fake_json(url):
            return submissions if "submissions" in url else index

        monkeypatch.setattr(sec_13f_scraper, "_http_get_json", fake_json)
        monkeypatch.setattr(
            sec_13f_scraper,
            "_http_get_text",
            lambda url: _info_table_xml(_row("APPLE INC", "037833100", 10, 5)),
        )
        filing = sec_13f_scraper.fetch_latest_13f_filing(fund)
        assert filing is not None
        assert filing.period_end_date == date(2026, 3, 31)
        assert filing.filed_date == date(2026, 5, 14)

    def test_filed_date_visible_in_detail_query(self, db):
        """The query layer already reads filed_date — verify end-to-end."""
        inst = _make_inst(db)
        filing = ScrapedFiling(
            code="sec-testfund",
            period_end_date=date(2026, 3, 31),
            total_value_usd=1_000,
            filed_date=date(2026, 5, 14),
        )
        institutional_service.upsert_filing(db, inst, filing)
        db.commit()
        detail = institutional_service.get_institutional_detail(db, "sec-testfund")
        assert detail is not None
        assert detail.filed_date == date(2026, 5, 14)


# ---------------------------------------------------------------------------
# 7. _find_recent_13fs (history walking)
# ---------------------------------------------------------------------------

class TestFindRecent13Fs:
    SUBMISSIONS = {
        "filings": {
            "recent": {
                "form": ["13F-HR/A", "13F-HR", "10-K", "13F-HR", "13F-HR", "13F-HR"],
                "accessionNumber": [
                    "acc-amend", "acc-q1-26", "acc-10k",
                    "acc-q4-25-restated", "acc-q4-25", "acc-q3-25",
                ],
                "reportDate": [
                    "2026-03-31", "2026-03-31", "2025-12-31",
                    "2025-12-31", "2025-12-31", "2025-09-30",
                ],
                "filingDate": [
                    "2026-05-20", "2026-05-14", "2026-02-01",
                    "2026-02-20", "2026-02-13", "2025-11-14",
                ],
            }
        }
    }

    def test_skips_amendments_and_dedupes_periods(self):
        entries = sec_13f_scraper._find_recent_13fs(self.SUBMISSIONS)
        # /A skipped; restated Q4 deduped keeping the newest; newest-first.
        assert [e[0] for e in entries] == [
            "acc-q1-26", "acc-q4-25-restated", "acc-q3-25",
        ]
        assert entries[0][1] == date(2026, 3, 31)
        assert entries[0][2] == date(2026, 5, 14)

    def test_limit_caps_the_walk(self):
        entries = sec_13f_scraper._find_recent_13fs(self.SUBMISSIONS, limit=2)
        assert [e[0] for e in entries] == ["acc-q1-26", "acc-q4-25-restated"]

    def test_latest_13f_delegates(self):
        acc, rd, fd = sec_13f_scraper._find_latest_13f(self.SUBMISSIONS)
        assert (acc, rd, fd) == (
            "acc-q1-26", date(2026, 3, 31), date(2026, 5, 14)
        )

    def test_no_13f_returns_none_triple(self):
        assert sec_13f_scraper._find_latest_13f(
            {"filings": {"recent": {"form": ["10-K"]}}}
        ) == (None, None, None)


# ---------------------------------------------------------------------------
# 8. Refresh-job style flow: resolution happens BEFORE persistence
# ---------------------------------------------------------------------------

class TestResolutionPersistFlow:
    def test_resolved_tickers_and_map_rows_land_in_db(self, db):
        db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc."))
        db.flush()

        filing = _filing_with(
            _cusip_holding("037833100", "APPLE INC", shares=100, value=1000),
            _cusip_holding("999999999", "OBSCURE MICROCAP LLC"),
        )
        catalog_map = sec_13f_scraper.build_name_to_ticker_map(
            db.execute(select(Stock)).scalars().all()
        )
        stats, new_res = sec_13f_scraper.resolve_filing_holdings(
            filing,
            cusip_map=sec_13f_scraper.load_cusip_ticker_map(db),
            catalog_map=catalog_map,
            sec_map={},
        )
        sec_13f_scraper.persist_cusip_resolutions(db, new_res)

        manager = ScrapedManager(code="999", slug="sec-testfund", name="Test Fund")
        summary = institutional_service.persist_scrape_results(
            db, [(manager, filing)], source="sec_13f", compute_qoq=True,
            type_resolver=lambda slug: "hedge_fund",
        )
        assert summary.holdings_inserted == 2

        f_row = db.execute(select(InstitutionalFiling)).scalars().one()
        tickers = {h.ticker for h in f_row.holdings}
        assert tickers == {"AAPL", "CUSIP:999999999"}
        assert sec_13f_scraper.load_cusip_ticker_map(db) == {"037833100": "AAPL"}
