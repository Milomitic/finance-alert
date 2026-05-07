"""News headline → analyst-action extractor.

yfinance's `Ticker.upgrades_downgrades` is the canonical source for
analyst rating changes, but it's stale for many tickers (sometimes
weeks behind the news cycle) and skips some firms entirely. The news
feed often surfaces fresher mentions in headline form:

    "Apple price target raised to $250 by Goldman Sachs"
    "Wedbush maintains Buy on NVIDIA, target $200"
    "Morgan Stanley downgrades Tesla to Equal-Weight"

This module turns those headlines into `AnalystAction` records the
fundamentals layer can merge with the structured upgrades_downgrades
list (deduping against same-firm same-day rows).

Limitations of headline-only extraction:
- We only see the title; body text where the actual target $ and
  prior grade live is unavailable. We extract what we can and leave
  unknowns as None.
- News headlines can be sloppy ("Apple stock rises after analyst
  raises target" — no firm named). Those titles return no match.
- Two headlines covering the same action (CNBC + Bloomberg both
  reporting "Goldman raises AAPL to $250") yield duplicate rows;
  we leave dedup to the merger which compares (firm, date).

Robustness:
- Conservative firm list — only well-known sell-side names. A title
  must match one of these to count. False positives from generic
  words like "Inc." are avoided by requiring a multi-word firm
  pattern when ambiguous.
- Action verbs are matched as standalone words via `\b...\b` so
  "lowered" doesn't accidentally match "lower-than-expected".
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Firm matchers — order matters: more specific patterns FIRST so the longer
# variant ("Bank of America Securities") wins over the shorter one ("Bank
# of America"). Each entry is (canonical_name, regex_pattern).
# ---------------------------------------------------------------------------

_FIRM_PATTERNS: tuple[tuple[str, str], ...] = (
    # Big banks / wirehouses
    ("Goldman Sachs",      r"\bGoldman(?:\s+Sachs)?\b"),
    ("Morgan Stanley",     r"\bMorgan\s+Stanley\b"),
    ("JPMorgan",           r"\bJ\.?P\.?\s*Morgan\b|\bJPMorgan\b"),
    ("Bank of America",    r"\bBank\s+of\s+America\b|\bBofA\b|\bBoA\b"),
    ("Wells Fargo",        r"\bWells\s+Fargo\b"),
    ("Citigroup",          r"\bCitigroup\b|\bCiti\b(?!group)"),
    ("HSBC",               r"\bHSBC\b"),
    ("UBS",                r"\bUBS\b"),
    ("Deutsche Bank",      r"\bDeutsche\s+Bank\b"),
    ("Credit Suisse",      r"\bCredit\s+Suisse\b"),
    ("Barclays",           r"\bBarclays\b"),
    ("BNP Paribas",        r"\bBNP\s+Paribas\b"),
    ("Mizuho",             r"\bMizuho\b"),
    ("Nomura",             r"\bNomura\b"),
    # Boutique / mid-tier sell-side
    ("Wedbush",            r"\bWedbush\b"),
    ("Jefferies",          r"\bJefferies\b"),
    ("Piper Sandler",      r"\bPiper\s+Sandler\b"),
    ("BMO Capital",        r"\bBMO\s+Capital\b|\bBMO\b"),
    ("RBC Capital",        r"\bRBC\s+Capital\b|\bRBC\b"),
    ("Raymond James",      r"\bRaymond\s+James\b"),
    ("KeyBanc",            r"\bKeyBanc\b"),
    ("Stifel",             r"\bStifel\b"),
    ("Cantor Fitzgerald",  r"\bCantor\s+Fitzgerald\b"),
    ("Truist",             r"\bTruist\b"),
    ("Oppenheimer",        r"\bOppenheimer\b"),
    ("Evercore ISI",       r"\bEvercore\s+ISI\b|\bEvercore\b"),
    ("Bernstein",          r"\bBernstein\b"),
    ("Argus",              r"\bArgus(?:\s+Research)?\b"),
    ("TD Cowen",           r"\bTD\s+Cowen\b|(?<!TD\s)\bCowen\b"),
    ("Loop Capital",       r"\bLoop\s+Capital\b"),
    ("Susquehanna",        r"\bSusquehanna\b|\bSIG\b"),
    ("Wolfe Research",     r"\bWolfe\s+Research\b"),
    ("Needham",            r"\bNeedham\b"),
    ("Roth MKM",           r"\bRoth\s+MKM\b"),
    ("D.A. Davidson",      r"\bD\.?A\.?\s+Davidson\b"),
    ("Tigress Financial",  r"\bTigress\s+Financial\b"),
    ("Citi",               r"\bCiti\b"),
    ("HSBC",               r"\bHSBC\b"),
)


# ---------------------------------------------------------------------------
# Action-verb classification. Any one of these in the headline plus a firm
# match is enough to call it an "analyst action". Order matters again:
# "downgrades" must match before "grades" / "lowers" before "lower" etc.
# ---------------------------------------------------------------------------

_ACTION_PATTERNS: tuple[tuple[str, str, str], ...] = (
    # (regex, action_code, price_target_action_label)
    (r"\b(?:downgrade[sd]?|cut[s]?\s+rating|lower[s]?\s+rating)\b", "down", "Downgrade"),
    (r"\b(?:upgrade[sd]?|rais(?:e|es|ed)\s+rating|boost[s]?\s+rating)\b", "up", "Upgrade"),
    (r"\b(?:initiate[sd]?|start(?:s|ed)?\s+coverage|begin(?:s|ning)?\s+coverage)\b", "init", "Initiates"),
    (r"\b(?:rais(?:e|es|ed)|boost(?:s|ed)?|lift(?:s|ed)?|increas(?:e|es|ed)|hik(?:e|es|ed))\b.{0,30}\btarget\b", "target_up", "Raises"),
    (r"\b(?:lower(?:s|ed)?|cut(?:s)?|slash(?:es|ed)?|trim(?:s|med)?|reduc(?:e|es|ed))\b.{0,30}\btarget\b", "target_down", "Lowers"),
    (r"\b(?:maintain(?:s|ed)?|reiterat(?:e|es|ed)|stick(?:s)?\s+with|keep[s]?|hold[s]?)\b.{0,30}\b(?:rating|outperform|buy|sell|hold|target)\b", "main", "Maintains"),
    (r"\bprice\s+target\b", "main", "Maintains"),  # generic "price target raised/cut" without explicit verb
)


# Two-step price-target extraction:
# 1. Title must mention "target" / "PT" / "price target" anywhere (gates
#    the search so a $-prefixed number elsewhere — e.g. revenue figures,
#    market cap mentions — doesn't get misread as a target).
# 2. THEN: pull the first plausible $-prefixed number out. Order of
#    proximity-to-target doesn't matter once the gate is open.
_TARGET_GATE_RE = re.compile(
    r"\b(?:price\s*target|target\s*price|target|PT)\b",
    re.IGNORECASE,
)
# $-prefixed number with optional comma thousand separator and 0-2 decimal
# places. Length 1–4 digits before the optional decimal: $5–$9999 covers
# every plausible per-share price (lowest blue chips ~$5, highest ~$5000
# for class-A Berkshire).
_DOLLAR_NUMBER_RE = re.compile(
    r"\$\s*([0-9]{1,4}(?:,[0-9]{3})?(?:\.[0-9]{1,2})?)\b"
)
# "to $X" — the conventional way English-language analyst notes name the
# NEW target ("raised target to $260", "from $245 to $260"). When both
# patterns appear in one sentence the "to $X" is the target the user
# cares about; the "from $X" is just historical context. Matching this
# explicitly prevents the naive first-$-wins logic from picking the
# prior target.
_DOLLAR_TO_RE = re.compile(
    r"\bto\s+\$\s*([0-9]{1,4}(?:,[0-9]{3})?(?:\.[0-9]{1,2})?)\b",
    re.IGNORECASE,
)


# Grade keywords: "Buy", "Hold", "Sell", "Outperform", "Neutral", etc. Used
# to populate `to_grade` when a headline declares a rating verbatim.
_GRADE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bStrong\s+Buy\b", "Strong Buy"),
    (r"\bOutperform\b", "Outperform"),
    (r"\bOverweight\b", "Overweight"),
    (r"\bMarket\s+Outperform\b", "Outperform"),
    (r"\bBuy\b", "Buy"),
    (r"\bAccumulate\b", "Buy"),
    (r"\bMarket\s+Perform\b", "Hold"),
    (r"\bEqual[\s-]?Weight\b", "Hold"),
    (r"\bNeutral\b", "Neutral"),
    (r"\bHold\b", "Hold"),
    (r"\bUnderperform\b", "Underperform"),
    (r"\bUnderweight\b", "Underperform"),
    (r"\bSell\b", "Sell"),
    (r"\bStrong\s+Sell\b", "Strong Sell"),
)


@dataclass
class ExtractedAnalystMention:
    """Parsed result from a single news headline.

    Field-mirrors `AnalystAction` so the merger can blit them in with
    minimal translation. `source_link` + `source_title` are extras the
    UI uses to render a "from news" badge with click-through.
    """
    date: str          # YYYY-MM-DD (taken from news.published_at)
    firm: str
    action: str        # "up" / "down" / "init" / "main" / "target_up" / "target_down"
    to_grade: str      # extracted grade or "" if absent
    from_grade: str    # always "" — news headlines rarely mention prior grade
    price_target_action: str | None  # "Raises" / "Lowers" / "Maintains" / "Initiates" / None
    current_price_target: float | None
    prior_price_target: float | None  # always None — same reason as from_grade
    source_link: str | None
    source_title: str


def extract_from_news_item(
    title: str,
    *,
    summary: str | None = None,
    published_at_iso: str | None = None,
    link: str | None = None,
) -> ExtractedAnalystMention | None:
    """Parse one news item (title + optional body summary).

    Returns None if neither title nor body looks like an analyst action.

    Strategy:
    1. Try the title first. Headlines have the highest signal-to-noise
       ratio (every word is curated for impact) so a title match wins
       and we skip the body.
    2. If title didn't match, fall back to the summary. Headlines often
       truncate ("Apple gets target hike") while the body spells out the
       firm + target ("Goldman raised its target from $245 to $260").
    3. Even when title matches, if it lacks a price target but the body
       has one, lift the target from the body. Price targets are the
       most useful field for the user, so we squeeze it out of whichever
       text source has it.

    Body-text caveat: summaries can mention historical analyst actions
    that aren't the current article's subject (e.g. "On Tuesday Goldman
    had raised the target..."). We accept that risk — false positives
    surface as a "news" badge with click-through to the article, so the
    user can verify on the source.

    The published_at_iso is parsed for the `YYYY-MM-DD` date. Parse
    failures fall through to empty date.
    """
    if not title and not summary:
        return None

    # Date once, used by both branches below.
    date_str = ""
    if published_at_iso:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", published_at_iso)
        if m:
            date_str = m.group(1)

    # First pass: title alone.
    title_mention = _try_extract(title, date_str=date_str, link=link, source_title=title)
    if title_mention is not None and title_mention.current_price_target is not None:
        # Best case — title matched AND has a price target. Done.
        return title_mention

    # Second pass: body. Either the title didn't match at all, or it
    # matched but didn't yield a price target — we'll use the body to
    # try to fill in the missing target.
    body_mention = (
        _try_extract(summary, date_str=date_str, link=link, source_title=title)
        if summary
        else None
    )

    if title_mention is not None and body_mention is not None:
        # Title matched (firm + action) but had no target; body matched
        # too. Prefer the title's firm classification (the article subject
        # is the firm in the headline) but lift the target from the body.
        if body_mention.current_price_target is not None:
            title_mention.current_price_target = body_mention.current_price_target
        return title_mention

    # Either title-only-match (no body match), or body-only-match,
    # or no match at all. Whichever is non-None wins.
    return title_mention or body_mention


def _try_extract(
    text: str | None,
    *,
    date_str: str,
    link: str | None,
    source_title: str,
) -> ExtractedAnalystMention | None:
    """Run the firm + action + target + grade pipeline against `text`.
    Shared by both the title and body passes in `extract_from_news_item`.
    """
    if not text:
        return None
    firm = _match_firm(text)
    if firm is None:
        return None
    action_match = _match_action(text)
    if action_match is None:
        return None
    action_code, pt_action_label = action_match
    return ExtractedAnalystMention(
        date=date_str,
        firm=firm,
        action=action_code,
        to_grade=_match_grade(text) or "",
        from_grade="",
        price_target_action=pt_action_label,
        current_price_target=_match_target(text),
        prior_price_target=None,
        source_link=link,
        source_title=source_title,
    )


# Back-compat alias — the old API took only a title. Existing callers
# that haven't been migrated to the news-item shape still work, just
# without the body-text fallback. New code should use
# `extract_from_news_item` directly.
def extract_from_title(
    title: str,
    *,
    published_at_iso: str | None = None,
    link: str | None = None,
) -> ExtractedAnalystMention | None:
    return extract_from_news_item(
        title,
        summary=None,
        published_at_iso=published_at_iso,
        link=link,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _match_firm(text: str) -> str | None:
    for canonical, pattern in _FIRM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return canonical
    return None


def _match_action(text: str) -> tuple[str, str] | None:
    """Return (action_code, price_target_action_label) on the first match."""
    for pattern, code, label in _ACTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return code, label
    return None


def _match_target(text: str) -> float | None:
    """Pull the most plausible $ price target out of the text.

    Three-step preference:
    1. Headline/body must mention "target"/"PT"/"price target" — without
       that gate, a $-figure could be revenue or market cap rather than
       a per-share target.
    2. PREFER "to $X" matches (`_DOLLAR_TO_RE`). Analyst notes using
       "from $245 to $260" or "raised target to $260" — the "to" target
       is the new one; without this preference the naive first-$-wins
       logic returns the historical prior target.
    3. Fall back to the first plausible $-prefixed number anywhere.

    Sanity-clamped to [5, 9999] — below $5 is almost always a percentage
    misparse, above $9999 a market-cap misparse.
    """
    if _TARGET_GATE_RE.search(text) is None:
        return None

    def _valid(raw: str) -> float | None:
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            return None
        return v if 5.0 <= v <= 9999.0 else None

    # Step 2: prefer the "to $X" form. Walk all matches (sentences may
    # have multiple "to $X" — pick the one closest to a target keyword).
    for m in _DOLLAR_TO_RE.finditer(text):
        v = _valid(m.group(1))
        if v is not None:
            return v

    # Step 3: fall back to first $-figure of any kind.
    for m in _DOLLAR_NUMBER_RE.finditer(text):
        v = _valid(m.group(1))
        if v is not None:
            return v
    return None


def _match_grade(text: str) -> str | None:
    for pattern, canonical in _GRADE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return canonical
    return None


# ---------------------------------------------------------------------------
# Merger — combines extracted news mentions with structured analyst actions
# ---------------------------------------------------------------------------

def _normalize_firm(firm: str) -> str:
    """Lowercase + strip trailing corporate suffixes for fuzzy matching.

    "Goldman Sachs Group, Inc." → "goldman sachs"
    "Bank of America Securities" → "bank of america"
    """
    s = firm.lower()
    s = re.sub(r"\s*(?:group|securities|capital|partners|llc|inc\.?|ltd\.?|plc|corp\.?|co\.?)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return " ".join(s.split())


def _date_within(d1: str, d2: str, days: int) -> bool:
    """Both ISO YYYY-MM-DD. Returns True iff |d1 - d2| <= days days.
    Empty/malformed inputs return False (won't match)."""
    if not d1 or not d2:
        return False
    try:
        from datetime import date

        a = date.fromisoformat(d1[:10])
        b = date.fromisoformat(d2[:10])
        return abs((a - b).days) <= days
    except (ValueError, TypeError):
        return False


def is_duplicate_of_existing(
    mention: ExtractedAnalystMention,
    existing: list,
    *,
    days_window: int = 3,
) -> bool:
    """Decide whether the news-extracted mention overlaps with a row we
    already have from yfinance's structured upgrades_downgrades.

    Duplicate iff: same normalized firm AND date within `days_window` days.
    The window absorbs publication delay (a Goldman action filed Tuesday
    might be reported by news outlets Wednesday morning).

    `existing` is duck-typed against `AnalystAction` (uses .firm + .date).
    Kept as `list` instead of `list[AnalystAction]` to avoid an import
    cycle — `stock_fundamentals_service` imports this module, this module
    can't import from it.
    """
    if not existing:
        return False
    norm_new = _normalize_firm(mention.firm)
    if not norm_new:
        return False
    for ex in existing:
        if _normalize_firm(getattr(ex, "firm", "") or "") != norm_new:
            continue
        if _date_within(mention.date, getattr(ex, "date", "") or "", days_window):
            return True
    return False
