"""SEC EDGAR 13F-HR direct scraper — Phase 2 of the institutional tracker.

Why SEC direct vs Dataroma (Phase 1):
- Dataroma curates value-investor portfolios; large index/quant managers
  (BlackRock, Vanguard, State Street, Bridgewater, Citadel, Renaissance)
  aren't on it. SEC EDGAR has every 13F filer in the US.
- 13F filings are quarterly with a 45-day delay (e.g. 2025-Q4 lands by
  Feb 14 2026). Reading them directly gives us positions for funds
  Dataroma doesn't track.
- The XML schema is stable: `<informationTable>` with `<infoTable>`
  rows containing nameOfIssuer / cusip / value / sshPrnamt.

Curation strategy:
- We DO NOT scrape every 13F filer (~6000 firms, mostly noise).
- We curate ~15 large institutionals + hedge funds NOT on Dataroma —
  ones whose positioning moves markets or signals macro views.
- Dataroma-tracked funds (Berkshire, Pabrai, Greenlight, Pershing) are
  excluded from this list to avoid duplicate rows in the UI.

Aggregation note:
- A single 13F can list the SAME `nameOfIssuer` / `cusip` multiple
  times when the firm splits positions across investment managers
  (Buffett vs Combs vs Weschler at Berkshire). The parser SUMs shares
  + value per CUSIP and emits a single ScrapedHolding per position.

CUSIP→ticker resolution:
- 13F gives us CUSIP + nameOfIssuer, NOT ticker. We resolve via name
  match against `Stock.name` in our catalog (normalized: uppercase,
  strip "INC"/"CORP"/"LLC"). When match fails, ticker is set to
  the CUSIP itself (rendered as text-only in the UI — same code
  path as off-catalog Dataroma tickers).

Q/Q deltas:
- 13F-HR doesn't include Q/Q deltas in the XML. We compute them at
  persistence time by joining with the previous quarter's filing
  (see `compute_qoq_deltas` in `institutional_service`). The first
  filing for a fund has no Q/Q data — `qoq_change_pct` stays null
  and `action` defaults to "hold".

Politeness:
- SEC requires a User-Agent that identifies who you are; without it
  every request returns 403. Format: "Name email@domain".
- Rate limit: 10 req/sec. We use 0.15s between requests for safety.
- Each fund needs 2 HTTP calls: submissions JSON + infotable XML.
  Total: ~30 calls for ~15 funds = 5s wall-clock.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable
from xml.etree import ElementTree as ET

import requests
from loguru import logger

from app.services.institutional_scraper import (
    ScrapedFiling,
    ScrapedHolding,
    ScrapedManager,
)

_USER_AGENT = "FinanceAlert milomitic@gmail.com"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/index.json"
)
_FILING_FILE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{filename}"
)
_REQUEST_TIMEOUT = 15.0
_POLITE_DELAY_SEC = 0.15  # SEC limit is 10/sec; we use ~6/sec for headroom

_INFOTABLE_NS = "{http://www.sec.gov/edgar/document/thirteenf/informationtable}"


# ---------------------------------------------------------------------------
# Curated list of CIKs to track (large institutional + hedge funds NOT on Dataroma)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CuratedFund:
    cik: int
    slug: str
    name: str
    manager_name: str | None
    type_: str  # "institutional" | "hedge_fund"
    description: str | None = None


# These CIKs were verified against EDGAR submissions JSON. Slugs prefixed
# with "sec-" so they don't collide with Dataroma slugs (which are 2-4
# char codes like "brk", "ako"). Names match SEC's own labeling for
# consistency in the UI.
CURATED_FUNDS: tuple[CuratedFund, ...] = (
    # ── Large index / multi-asset managers ─────────────────────────────
    # NOTE on CIKs: the legacy "BLACKROCK INC." CIK 1086364 stopped filing
    # 13F-HR after 2016 when BlackRock consolidated reporting under a new
    # corporate entity (CIK 2012383). Verifying via SEC full-text search
    # before adding new funds is mandatory — a stale CIK silently returns
    # ancient filings instead of failing loudly.
    CuratedFund(2012383, "sec-blackrock", "BlackRock Inc.", None, "institutional",
                "Largest asset manager globally; iShares ETF complex."),
    CuratedFund(102909, "sec-vanguard", "Vanguard Group Inc.", None, "institutional",
                "Index-fund pioneer; second-largest asset manager."),
    CuratedFund(93751, "sec-state-street", "State Street Corp.", None, "institutional",
                "Custody bank; SPDR ETF family."),
    CuratedFund(315066, "sec-fidelity", "FMR LLC (Fidelity)", None, "institutional",
                "Mutual-fund and brokerage giant; private."),
    CuratedFund(80255, "sec-trowe", "T. Rowe Price Group", None, "institutional",
                "Active mutual-fund manager."),
    CuratedFund(1214717, "sec-geode", "Geode Capital Management", None, "institutional",
                "Quant subadvisor for many Fidelity index funds."),
    # ── Quant / multi-strat hedge funds ────────────────────────────────
    CuratedFund(1350694, "sec-bridgewater", "Bridgewater Associates", "Ray Dalio", "hedge_fund",
                "Largest hedge fund globally; All Weather / Pure Alpha."),
    CuratedFund(1037389, "sec-renaissance", "Renaissance Technologies", "Jim Simons (founder)", "hedge_fund",
                "Quantitative-trading pioneer; Medallion Fund (closed external)."),
    CuratedFund(1423053, "sec-citadel", "Citadel Advisors", "Ken Griffin", "hedge_fund",
                "Multi-strategy hedge fund + Citadel Securities market-maker."),
    CuratedFund(1179392, "sec-two-sigma", "Two Sigma Investments", "John Overdeck / David Siegel", "hedge_fund",
                "Quantitative hedge fund using ML/big-data approaches."),
    CuratedFund(1273087, "sec-millennium", "Millennium Management", "Israel Englander", "hedge_fund",
                "Multi-PM platform; one of the largest pod shops."),
    CuratedFund(1009207, "sec-de-shaw", "D.E. Shaw & Co.", "David Shaw (founder)", "hedge_fund",
                "Quantitative + discretionary hybrid; HF + venture arm."),
    CuratedFund(1167557, "sec-aqr", "AQR Capital Management", "Cliff Asness", "hedge_fund",
                "Factor-investing pioneer; quantitative value/momentum."),
    CuratedFund(1218710, "sec-balyasny", "Balyasny Asset Management", "Dmitry Balyasny", "hedge_fund",
                "Multi-strategy / multi-PM platform."),
    CuratedFund(1603466, "sec-point72", "Point72 Asset Management", "Steven A. Cohen", "hedge_fund",
                "Successor to SAC Capital; long/short equity."),
    # ── Phase 3: additional discretionary / activist / sovereign funds ──
    # The original spec called for HedgeFollow as Phase 3, but their
    # holdings data is gated behind a paid subscription (the public
    # pages only expose fund-level metadata: AUM, manager name,
    # # of holdings — the per-position table requires login). We
    # pivoted to extending the SEC 13F coverage with additional funds
    # NOT on Dataroma. Same end-user value (more institutional data
    # tracked), no scraping fragility.
    CuratedFund(1029160, "sec-soros", "Soros Fund Management", "George Soros / Robert Soros", "hedge_fund",
                "Macro-focused family office (formerly Quantum Fund)."),
    CuratedFund(1517137, "sec-starboard", "Starboard Value LP", "Jeff Smith", "hedge_fund",
                "Activist hedge fund focused on operational turnarounds."),
    CuratedFund(1135730, "sec-coatue", "Coatue Management", "Philippe Laffont", "hedge_fund",
                "Tiger Cub focused on technology / consumer growth."),
    CuratedFund(1318757, "sec-marshall-wace", "Marshall Wace LLP", "Paul Marshall / Ian Wace", "hedge_fund",
                "London-based long/short equity multi-manager."),
    CuratedFund(1422848, "sec-capital-research", "Capital Research Global Investors", None, "institutional",
                "Capital Group global equity team (American Funds)."),
    CuratedFund(1562230, "sec-capital-international", "Capital International Investors", None, "institutional",
                "Capital Group international equity team."),
    CuratedFund(1374170, "sec-norges-bank", "Norges Bank Investment Management", None, "institutional",
                "Norway sovereign wealth fund (~$1.5T AUM)."),
    CuratedFund(1666335, "sec-rokos", "Rokos Capital Management LLP", "Chris Rokos", "hedge_fund",
                "Macro-focused hedge fund (Brevan Howard alum)."),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_curated_funds() -> tuple[CuratedFund, ...]:
    """Expose the curated list to the seed script + cron job."""
    return CURATED_FUNDS


def fetch_latest_13f_filing(fund: CuratedFund) -> ScrapedFiling | None:
    """Fetch the latest 13F-HR filing for `fund.cik`.

    Returns None on:
      - HTTP error fetching submissions JSON
      - No 13F-HR in the recent filings list
      - HTTP error fetching the information table XML
      - XML that doesn't conform to the expected schema

    The caller (the cron + seed script) just skips the fund and logs.
    """
    submissions = _http_get_json(_SUBMISSIONS_URL.format(cik=fund.cik))
    if submissions is None:
        return None

    accession, report_date, filing_date = _find_latest_13f(submissions)
    if accession is None:
        logger.warning(f"[sec_13f] {fund.slug}: no 13F-HR in recent filings")
        return None

    info_table_xml = _fetch_info_table_xml(fund.cik, accession)
    if info_table_xml is None:
        return None

    holdings = list(_parse_info_table(info_table_xml))
    holdings = _aggregate_by_cusip(holdings)
    total_value = sum(h.value_usd or 0 for h in holdings) or None

    return ScrapedFiling(
        code=fund.slug,
        period_end_date=report_date,
        total_value_usd=total_value,
        holdings=holdings,
    )


def fetch_all_curated() -> list[tuple[ScrapedManager, ScrapedFiling | None]]:
    """Iterate the curated CIK list, fetch each fund's latest 13F.

    Returns the same shape as `institutional_scraper.scrape_all_portfolios`
    so the persistence layer (`institutional_service.persist_scrape_results`)
    can consume both transparently.
    """
    out: list[tuple[ScrapedManager, ScrapedFiling | None]] = []
    for fund in CURATED_FUNDS:
        manager = ScrapedManager(
            code=str(fund.cik),
            slug=fund.slug,
            name=fund.name,
            manager_name=fund.manager_name,
            source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={fund.cik}&type=13F",
            description=fund.description,
        )
        try:
            filing = fetch_latest_13f_filing(fund)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[sec_13f] {fund.slug}: error {e}")
            filing = None
        out.append((manager, filing))
        time.sleep(_POLITE_DELAY_SEC)
    return out


# ---------------------------------------------------------------------------
# HTTP + parsing helpers
# ---------------------------------------------------------------------------

def _http_get_json(url: str) -> dict | None:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(f"[sec_13f] GET {url} -> {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[sec_13f] GET {url} failed: {e}")
        return None


def _http_get_text(url: str) -> str | None:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/xml,text/xml"},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(f"[sec_13f] GET {url} -> {resp.status_code}")
            return None
        return resp.text
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[sec_13f] GET {url} failed: {e}")
        return None


def _find_latest_13f(submissions: dict) -> tuple[str | None, date | None, date | None]:
    """Walk submissions["filings"]["recent"] and return the (accession,
    report_date, filing_date) of the most recent 13F-HR.

    Returns (None, None, None) if no 13F-HR is in the recent slice.
    `recent` is bounded to the last ~1000 filings; for our funds that's
    decades of history, more than enough."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms: list[str] = recent.get("form", [])
    accessions: list[str] = recent.get("accessionNumber", [])
    report_dates: list[str] = recent.get("reportDate", [])
    filing_dates: list[str] = recent.get("filingDate", [])

    # 13F-HR is the standard filer; 13F-HR/A is an amendment (we skip
    # amendments to avoid double-counting against the original).
    for i, form in enumerate(forms):
        if form == "13F-HR":
            acc = accessions[i] if i < len(accessions) else None
            rd = _parse_iso_date(report_dates[i] if i < len(report_dates) else "")
            fd = _parse_iso_date(filing_dates[i] if i < len(filing_dates) else "")
            return acc, rd, fd
    return None, None, None


def _parse_iso_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _fetch_info_table_xml(cik: int, accession: str) -> str | None:
    """Resolve the information-table XML URL via the filing index.

    The information table file's name varies (e.g. "50240.xml",
    "infotable.xml", "form13fInfoTable.xml"). We list the directory
    via index.json and pick the largest XML file that ISN'T
    primary_doc.xml (the cover page is small; the info table is big).
    """
    acc_clean = accession.replace("-", "")
    cik_int = str(cik)
    idx = _http_get_json(_FILING_INDEX_URL.format(cik_int=cik_int, acc_clean=acc_clean))
    if idx is None:
        return None
    items = idx.get("directory", {}).get("item", [])
    # Pick largest .xml file excluding primary_doc.xml. SEC stores `size`
    # as a string; convert defensively.
    candidates: list[tuple[int, str]] = []
    for it in items:
        name = it.get("name", "")
        if not name.lower().endswith(".xml"):
            continue
        if name.lower() == "primary_doc.xml":
            continue
        try:
            size = int(it.get("size") or 0)
        except (ValueError, TypeError):
            size = 0
        candidates.append((size, name))
    if not candidates:
        logger.warning(
            f"[sec_13f] no info-table XML found in filing {cik}/{accession}"
        )
        return None
    candidates.sort(reverse=True)
    filename = candidates[0][1]
    url = _FILING_FILE_URL.format(cik_int=cik_int, acc_clean=acc_clean, filename=filename)
    return _http_get_text(url)


def _parse_info_table(xml_text: str) -> Iterable[ScrapedHolding]:
    """Parse the 13F information-table XML into ScrapedHolding rows.

    Each `<infoTable>` becomes one holding. Aggregation across multiple
    rows for the same CUSIP happens in `_aggregate_by_cusip` AFTER
    parsing — keep this function pure-ish.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"[sec_13f] XML parse error: {e}")
        return

    for entry in root.findall(f"{_INFOTABLE_NS}infoTable"):
        try:
            issuer = (entry.findtext(f"{_INFOTABLE_NS}nameOfIssuer") or "").strip()
            cusip = (entry.findtext(f"{_INFOTABLE_NS}cusip") or "").strip()
            value_text = entry.findtext(f"{_INFOTABLE_NS}value") or ""
            shrs_node = entry.find(f"{_INFOTABLE_NS}shrsOrPrnAmt")
            shares_text = ""
            ssh_type = ""
            if shrs_node is not None:
                shares_text = shrs_node.findtext(f"{_INFOTABLE_NS}sshPrnamt") or ""
                ssh_type = (
                    shrs_node.findtext(f"{_INFOTABLE_NS}sshPrnamtType") or ""
                ).strip().upper()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[sec_13f] row parse error: {e}")
            continue

        # Skip non-share holdings (PRN = principal amount = bonds).
        if ssh_type and ssh_type != "SH":
            continue
        if not cusip or not issuer:
            continue

        try:
            value_usd = int(value_text)
        except (ValueError, TypeError):
            value_usd = None
        try:
            shares = int(shares_text)
        except (ValueError, TypeError):
            shares = None

        # 13F doesn't expose ticker — use CUSIP as a placeholder; the
        # service layer resolves to the catalog ticker via name match
        # at persistence time. CUSIP-based ticker still renders cleanly
        # in the UI as text-only (same as off-catalog Dataroma tickers).
        ticker_placeholder = f"CUSIP:{cusip}"

        yield ScrapedHolding(
            ticker=ticker_placeholder,
            company_name=issuer,
            shares=shares,
            value_usd=value_usd,
            portfolio_pct=None,  # Filled in `_compute_portfolio_pct`
            qoq_change_pct=None,  # Computed at persistence by Q/Q join
            qoq_change_shares=None,
            action=None,  # Computed at persistence by Q/Q join
        )


def _aggregate_by_cusip(holdings: list[ScrapedHolding]) -> list[ScrapedHolding]:
    """Sum shares + value across rows that share the same CUSIP.

    13F filings split positions across investment managers (Berkshire's
    AAPL is reported by Buffett's manager + Combs's manager + Weschler's
    manager separately). Our schema keeps one row per (filing, ticker),
    so we collapse here. Picks the most-common nameOfIssuer for cosmetic
    consistency.
    """
    by_cusip: dict[str, ScrapedHolding] = {}
    for h in holdings:
        # ticker is "CUSIP:<id>" at this point — use it as the dedupe key.
        key = h.ticker
        if key in by_cusip:
            cur = by_cusip[key]
            cur.shares = (cur.shares or 0) + (h.shares or 0)
            cur.value_usd = (cur.value_usd or 0) + (h.value_usd or 0)
        else:
            by_cusip[key] = h

    aggregated = list(by_cusip.values())
    _compute_portfolio_pct(aggregated)
    return aggregated


def _compute_portfolio_pct(holdings: list[ScrapedHolding]) -> None:
    """Mutate `holdings` in place: compute portfolio_pct from value_usd."""
    total = sum(h.value_usd or 0 for h in holdings)
    if total <= 0:
        return
    for h in holdings:
        if h.value_usd is None:
            continue
        h.portfolio_pct = round((h.value_usd / total) * 100, 4)


# ---------------------------------------------------------------------------
# Catalog name match — CUSIP placeholder → real ticker
# ---------------------------------------------------------------------------

_NAME_NORMALIZER_RE = re.compile(r"[^A-Z0-9]+")
_COMMON_SUFFIXES = (
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD",
    "LIMITED", "LLC", "PLC", "AG", "SA", "NV", "HOLDINGS", "HOLDING",
    "GROUP", "GRP", "CL", "CLA", "CLB", "CLC", "COM", "ORD", "TRUST",
    "REIT",
)


def normalize_issuer_name(name: str) -> str:
    """Collapse "Apple Inc." / "APPLE INC" / "Apple Inc Common Stock" to
    a single canonical form ("APPLE") for matching against `Stock.name`."""
    if not name:
        return ""
    s = name.upper()
    # Strip parentheticals "(NEW)" "(CL A)" etc.
    s = re.sub(r"\([^)]*\)", " ", s)
    # Tokenize and drop common corporate suffixes.
    tokens = [t for t in _NAME_NORMALIZER_RE.split(s) if t]
    tokens = [t for t in tokens if t not in _COMMON_SUFFIXES]
    return " ".join(tokens)


def build_name_to_ticker_map(stocks_iter: Iterable) -> dict[str, str]:
    """Build a normalized-name → ticker map from a Stock iterable.

    Caller passes the Stock ORM rows. We deliberately don't import Stock
    here so this module stays import-cheap (the cron job and seed script
    handle the DB session)."""
    out: dict[str, str] = {}
    for s in stocks_iter:
        norm = normalize_issuer_name(getattr(s, "name", "") or "")
        if not norm:
            continue
        # First-write-wins. Catalog has duplicates; either row works.
        out.setdefault(norm, getattr(s, "ticker", ""))
    return out


def resolve_holdings_against_catalog(
    holdings: list[ScrapedHolding],
    name_to_ticker: dict[str, str],
) -> tuple[int, int]:
    """Mutate `holdings` in place: replace "CUSIP:xxx" placeholders with
    real catalog tickers when the issuer name matches.

    Returns (resolved, unresolved) for logging.
    """
    resolved = 0
    unresolved = 0
    for h in holdings:
        if not h.ticker.startswith("CUSIP:"):
            continue
        norm = normalize_issuer_name(h.company_name or "")
        if norm and norm in name_to_ticker:
            h.ticker = name_to_ticker[norm]
            resolved += 1
        else:
            unresolved += 1
    return resolved, unresolved
