"""Dataroma scraper - parses the curated "Superinvestors" portfolios.

Why Dataroma vs SEC EDGAR direct:
- Dataroma curates ~80 portfolios of well-known investors (Buffett,
  Munger, Burry, Klarman, Pabrai, Watsa, ...) and presents them as
  clean HTML tables with Q/Q delta + action labels already computed.
  SEC 13F XML requires per-fund cusip resolution and Q/Q join logic.
- Dataroma uses its own internal "manager codes" (e.g. "BRK" for
  Berkshire); those are stable and we use them as the `slug`.

Endpoints scraped:
  - https://www.dataroma.com/m/managers.php           (manager index)
  - https://www.dataroma.com/m/holdings.php?m={code}  (one portfolio)

Robustness:
- Every parse step wrapped in try/except. A schema drift (Dataroma
  rebrand, table column rename) logs a warning but doesn't crash the
  scrape; the partial result still imports.
- Polite rate limiting: 1.0s sleep between portfolio fetches. With
  ~80 portfolios that's ~90s wall-clock for a full refresh — well
  within Dataroma's tolerance for non-abusive scrapers.
- HTTP timeout 15s per request; retries handled by the caller (we
  don't do exponential backoff here — a transient failure means the
  refresh skips that one portfolio and tries again next week).

The data lifecycle is QUARTERLY (13F deadline). Refreshing more than
once a week is wasteful; the cron is sat 04:00 by convention.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from loguru import logger


_BASE_URL = "https://www.dataroma.com"
_INDEX_URL = f"{_BASE_URL}/m/managers.php"
_HOLDINGS_URL = f"{_BASE_URL}/m/holdings.php?m={{code}}"
_USER_AGENT = (
    "Mozilla/5.0 (compatible; FinanceAlert/1.0; +personal-use)"
)
_REQUEST_TIMEOUT = 15.0
_POLITE_DELAY_SEC = 1.0


@dataclass
class ScrapedManager:
    """One row from the managers index. Lightweight metadata for upsert."""
    code: str  # Dataroma internal id, e.g. "BRK"
    slug: str  # url-safe lowercased version, e.g. "brk"
    name: str  # "Berkshire Hathaway"
    manager_name: str | None = None  # "Warren Buffett"
    source_url: str | None = None
    description: str | None = None


@dataclass
class ScrapedHolding:
    """One row from a portfolio holdings table."""
    ticker: str
    company_name: str | None
    shares: int | None
    value_usd: int | None
    portfolio_pct: float | None
    qoq_change_pct: float | None
    qoq_change_shares: int | None
    action: str | None  # "new"|"add"|"reduce"|"sold_out"|"hold"


@dataclass
class ScrapedFiling:
    """A full portfolio snapshot ready for persistence."""
    code: str
    period_end_date: date | None  # parsed from the page header
    total_value_usd: int | None
    holdings: list[ScrapedHolding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_managers_index() -> list[ScrapedManager]:
    """Fetch the Dataroma managers index page and parse the listed
    portfolios.

    Returns a list of ScrapedManager metadata. The names + manager
    person + URL are extracted from the link rows; if the structure
    drifts we fall back to a defensive parse that still captures
    `code` + `name` and leaves the rest None.
    """
    html = _http_get(_INDEX_URL)
    if html is None:
        logger.warning("[institutional_scraper] managers index fetch failed")
        return []
    soup = BeautifulSoup(html, "html.parser")

    out: list[ScrapedManager] = []
    seen: set[str] = set()
    # Each portfolio is linked via /m/holdings.php?m=CODE. Walk all
    # such links from the index page; dedupe by code.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"holdings\.php\?m=([A-Za-z0-9_-]+)", href)
        if not m:
            continue
        code = m.group(1)
        if code in seen:
            continue
        seen.add(code)
        # Link text format: "Manager Name - Portfolio Name" or just
        # "Portfolio Name". We treat the whole link text as `name`
        # and try to split on " - " for manager + portfolio.
        text = a.get_text(strip=True)
        if not text:
            continue
        manager_name: str | None = None
        portfolio_name = text
        if " - " in text:
            parts = [p.strip() for p in text.split(" - ", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                manager_name, portfolio_name = parts[0], parts[1]
        out.append(
            ScrapedManager(
                code=code,
                slug=_make_slug(code),
                name=portfolio_name,
                manager_name=manager_name,
                source_url=f"{_BASE_URL}/{href.lstrip('/')}",
            )
        )
    logger.info(f"[institutional_scraper] index: {len(out)} portfolios discovered")
    return out


def scrape_portfolio(code: str) -> ScrapedFiling | None:
    """Fetch and parse one portfolio's holdings page.

    Returns None on HTTP failure. On parse failure, returns a partial
    ScrapedFiling with whatever rows could be extracted — the caller
    decides whether to persist a thin filing.
    """
    url = _HOLDINGS_URL.format(code=code)
    html = _http_get(url)
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")

    period_end = _parse_period_end(soup)
    total_value = _parse_total_value(soup)
    holdings = list(_parse_holdings_rows(soup))
    return ScrapedFiling(
        code=code,
        period_end_date=period_end,
        total_value_usd=total_value,
        holdings=holdings,
    )


def scrape_all_portfolios(
    managers: Iterable[ScrapedManager],
    *,
    delay_sec: float = _POLITE_DELAY_SEC,
) -> list[tuple[ScrapedManager, ScrapedFiling | None]]:
    """Iterate the manager list, fetch each portfolio, sleep between
    requests for politeness. Returns the full result set so the
    persistence layer can upsert atomically per manager.
    """
    out: list[tuple[ScrapedManager, ScrapedFiling | None]] = []
    for i, m in enumerate(managers, start=1):
        try:
            filing = scrape_portfolio(m.code)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[institutional_scraper] {m.code} ({m.name}): scrape error {e}"
            )
            filing = None
        out.append((m, filing))
        if i < len(list(managers)) if not isinstance(managers, list) else i < len(managers):
            time.sleep(delay_sec)
    return out


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

def _http_get(url: str) -> str | None:
    """Single GET with timeout + UA. None on any error."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(
                f"[institutional_scraper] GET {url} -> {resp.status_code}"
            )
            return None
        return resp.text
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[institutional_scraper] GET {url} failed: {e}")
        return None


def _make_slug(code: str) -> str:
    """Dataroma codes are short alnum strings already. Lowercase for
    URL stability across our routes (`/institutionals/{slug}`)."""
    return re.sub(r"[^a-z0-9-]", "-", code.lower()).strip("-")


def _parse_period_end(soup: BeautifulSoup) -> date | None:
    """Dataroma's holdings page header carries text like
    "Period: Q1 2026" or "Period: Mar 31, 2026". Try a few patterns;
    return None if we can't pin it down — caller persists null and
    the UI shows "Latest filing"."""
    for tag in soup.find_all(["h1", "h2", "p", "span", "div"]):
        text = tag.get_text(" ", strip=True)
        if not text or "period" not in text.lower():
            continue
        # Pattern 1: "Mar 31, 2026" -- explicit date
        m = re.search(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})",
            text,
        )
        if m:
            try:
                return datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y"
                ).date()
            except ValueError:
                pass
        # Pattern 2: "Q1 2026" -- quarter label, map to quarter end
        m = re.search(r"\bQ([1-4])\s+(\d{4})", text)
        if m:
            q = int(m.group(1))
            y = int(m.group(2))
            month_day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[q]
            return date(y, *month_day)
    return None


def _parse_total_value(soup: BeautifulSoup) -> int | None:
    """Look for "Total Value: $X" near the page header."""
    for tag in soup.find_all(["p", "span", "div", "h2", "h3"]):
        text = tag.get_text(" ", strip=True)
        if "total value" not in text.lower():
            continue
        # Pull the first dollar-amount-like substring after the label
        m = re.search(r"\$([0-9,\.]+)\s*(B|M|bn|mn|billion|million)?", text, re.I)
        if not m:
            continue
        try:
            num = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        if unit.startswith("b"):
            return int(num * 1_000_000_000)
        if unit.startswith("m"):
            return int(num * 1_000_000)
        return int(num)
    return None


def _parse_holdings_rows(soup: BeautifulSoup) -> Iterable[ScrapedHolding]:
    """Walk the largest <table> on the page (Dataroma puts holdings in
    one big table) and extract one ScrapedHolding per <tr>.

    Real Dataroma column layout (observed 2026-Q1):
        [0] History (≡ icon)
        [1] Stock (Ticker - Name)
        [2] % of Portfolio
        [3] Recent Activity ("Reduce 0.34%" / "Add 12.5%" / "New" / etc.)
        [4] Shares
        [5] Reported Price
        [6] Value ($USD)
        [7] (empty)
        [8] Current Price
        [9] +/- Reported Price (PRICE delta — NOT position delta)
        [10] 52 Week Low
        [11] 52 Week High

    Headers live in the FIRST <tr> as <td> cells (no <thead> / <th>).
    We detect this and skip the first row when iterating data rows.

    Q/Q position change is encoded inside the Recent Activity cell:
    "Reduce 0.34%" → -0.34, "Add 12.5%" → +12.5, "New" → null,
    "Sold out" → null. Column 9 is the PRICE delta, not the
    position delta — don't confuse them.
    """
    table = _largest_table(soup)
    if table is None:
        return
    rows = table.find_all("tr")
    if not rows:
        return

    # Try <th> first; fall back to first <tr>'s <td> as headers (Dataroma layout).
    th_headers = [
        th.get_text(" ", strip=True).lower() for th in table.find_all("th")
    ]
    if th_headers:
        headers = th_headers
        data_rows_start = 0
    else:
        first_cells = rows[0].find_all("td")
        headers = [c.get_text(" ", strip=True).lower() for c in first_cells]
        # First row IS the header — skip it for data iteration.
        data_rows_start = 1
    col_idx = _resolve_columns(headers)

    for tr in rows[data_rows_start:]:
        cells = tr.find_all("td")
        if not cells:
            continue
        try:
            yield from _parse_one_row(cells, col_idx)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[institutional_scraper] row parse error: {e}")


def _largest_table(soup: BeautifulSoup) -> BeautifulSoup | None:
    """Return the <table> with the most rows — Dataroma's layout puts
    other small tables for nav/meta so the holdings table is invariably
    the biggest."""
    tables = soup.find_all("table")
    if not tables:
        return None
    return max(tables, key=lambda t: len(t.find_all("tr")))


def _resolve_columns(headers: list[str]) -> dict[str, int]:
    """Build a label → column-index map. Falls back to canonical
    Dataroma offsets when label matching fails.

    Real headers (lowercased): ['history', 'stock', '% of portfolio',
    'recent activity', 'shares', 'reported price*', 'value', '',
    'current price', '+/- reported price', '52 week low', '52 week high']
    """
    idx: dict[str, int] = {}
    for i, h in enumerate(headers):
        h = h.lower().strip()
        if not h:
            continue
        # Order matters: more specific labels first.
        if "portfolio" in h and "%" in h:
            idx.setdefault("pct_portfolio", i)
        elif "recent" in h and "activity" in h:
            idx.setdefault("activity", i)
        elif "share" in h and "report" not in h:
            idx.setdefault("shares", i)
        elif h == "stock" or (h.startswith("stock") and "share" not in h):
            idx.setdefault("stock", i)
        elif h == "value" or (h.startswith("value") or "$ value" in h):
            idx.setdefault("value", i)
    # Canonical Dataroma "Holdings" layout — used when label matching
    # missed a key. These are the indices observed at 2026-Q1; if
    # Dataroma rebrands and labels stop matching, the dynamic resolution
    # above kicks in and these become irrelevant.
    idx.setdefault("stock", 1)
    idx.setdefault("pct_portfolio", 2)
    idx.setdefault("activity", 3)
    idx.setdefault("shares", 4)
    idx.setdefault("value", 6)
    return idx


def _parse_one_row(
    cells: list, idx: dict[str, int]
) -> Iterable[ScrapedHolding]:
    """One <tr> -> at most one ScrapedHolding."""
    if len(cells) <= idx.get("stock", 1):
        return

    stock_text = cells[idx["stock"]].get_text(" ", strip=True)
    # Format: "AAPL - Apple Inc" or "BRK.B - Berkshire ..."
    ticker = stock_text
    company = None
    if " - " in stock_text:
        ticker, company = [s.strip() for s in stock_text.split(" - ", 1)]
    if not ticker:
        return
    # Strip parenthetical exchange suffixes "AAPL (NASDAQ)"
    ticker = re.sub(r"\s*\(.*?\)\s*$", "", ticker).strip()
    if not ticker or len(ticker) > 32:
        return

    shares = _parse_int(_cell_text(cells, idx.get("shares")))
    pct_port = _parse_pct(_cell_text(cells, idx.get("pct_portfolio")))
    value = _parse_money(_cell_text(cells, idx.get("value")))
    activity = _cell_text(cells, idx.get("activity")) or ""
    action = _classify_action(activity)
    # Q/Q POSITION change is encoded inside the Recent Activity cell:
    # "Reduce 0.34%" → -0.34, "Add 12.5%" → +12.5, "New" / "Sold out" → null.
    # Sign is inferred from the verb (reduce/sell → negative).
    pct_change = _qoq_from_activity(activity, action)

    yield ScrapedHolding(
        ticker=ticker.upper(),
        company_name=company,
        shares=shares,
        value_usd=value,
        portfolio_pct=pct_port,
        qoq_change_pct=pct_change,
        qoq_change_shares=None,  # Dataroma doesn't expose absolute Δshares directly
        action=action,
    )


def _qoq_from_activity(activity: str, action: str | None) -> float | None:
    """Extract Q/Q position change from a "Recent Activity" cell.

    Examples:
      "Add 12.5%"      → +12.5
      "Reduce 0.34%"   → -0.34
      "New"            → None (no prior baseline to compare against)
      "Sold Out"       → None (Dataroma doesn't quote a specific %)
      ""               → None
    """
    if not activity or action in (None, "new", "sold_out", "hold"):
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", activity)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if action == "reduce":
        return -val
    return val


def _cell_text(cells: list, i: int | None) -> str:
    if i is None or i >= len(cells):
        return ""
    return cells[i].get_text(" ", strip=True)


def _parse_int(s: str) -> int | None:
    if not s:
        return None
    s = s.replace(",", "").strip()
    m = re.match(r"^-?\d+", s)
    if not m:
        return None
    try:
        return int(m.group())
    except ValueError:
        return None


def _parse_pct(s: str) -> float | None:
    if not s:
        return None
    m = re.search(r"-?\d+(\.\d+)?", s.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _parse_money(s: str) -> int | None:
    """Parse "$1,234,567" or "$1.5B" to integer USD."""
    if not s:
        return None
    s = s.replace(",", "").strip().lstrip("$")
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*([KMB])?", s, re.I)
    if not m:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    unit = (m.group(2) or "").upper()
    mult = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(unit, 1)
    return int(num * mult)


def _classify_action(text: str) -> str | None:
    """Map Dataroma activity tags to our 5-value action enum."""
    t = text.strip().lower()
    if not t:
        return None
    if "new" in t:
        return "new"
    if "add" in t:
        return "add"
    if "reduce" in t or "sell" in t and "out" not in t:
        return "reduce"
    if "sold out" in t or "sell out" in t:
        return "sold_out"
    return "hold"
