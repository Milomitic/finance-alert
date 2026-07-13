"""Unit tests for the SEC point-in-time fundamentals parser + PIT
query helpers. All synthetic — no network. The live SEC API is
exercised manually (see the module docstring); here we lock the
parsing + PIT-discipline logic so a refactor can't silently break
look-ahead protection."""
from datetime import date

from app.services import sec_fundamentals_history as sf


def _companyfacts_fixture() -> dict:
    """Minimal companyfacts shape: two revenue tags (era fallback),
    quarterly + annual durations, with distinct filed dates."""
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            # FY2018 annual, filed late 2018
                            {"end": "2018-12-31", "start": "2018-01-01",
                             "val": 100_000, "filed": "2019-02-01", "form": "10-K"},
                        ]
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            # 4 quarters of 2019, each ~91 days
                            {"end": "2019-03-31", "start": "2019-01-01",
                             "val": 30_000, "filed": "2019-05-01", "form": "10-Q"},
                            {"end": "2019-06-30", "start": "2019-04-01",
                             "val": 31_000, "filed": "2019-08-01", "form": "10-Q"},
                            {"end": "2019-09-30", "start": "2019-07-01",
                             "val": 32_000, "filed": "2019-11-01", "form": "10-Q"},
                            {"end": "2019-12-31", "start": "2019-10-01",
                             "val": 33_000, "filed": "2020-02-01", "form": "10-Q"},
                        ]
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {"end": "2019-03-31", "val": 500_000,
                             "filed": "2019-05-01", "form": "10-Q"},
                            {"end": "2019-12-31", "val": 550_000,
                             "filed": "2020-02-01", "form": "10-K"},
                        ]
                    }
                },
            }
        }
    }


def test_parse_merges_fallback_tags():
    parsed = sf._parse_companyfacts(_companyfacts_fixture())
    # Revenue series merges both tags → 1 annual + 4 quarterly = 5 points.
    rev = parsed["revenue"]
    assert len(rev) == 5
    # Quarterly points carry a ~91-day duration; the annual ~365.
    durs = sorted({p.duration_days for p in rev if p.duration_days})
    assert any(85 <= d <= 100 for d in durs)   # quarterly present
    assert any(350 <= d <= 380 for d in durs)  # annual present


def test_instant_concept_has_no_duration():
    parsed = sf._parse_companyfacts(_companyfacts_fixture())
    eq = parsed["equity"]
    assert all(p.duration_days is None for p in eq)


def test_latest_instant_respects_filed_date():
    """PIT discipline: a value filed AFTER the as-of date must not be
    visible. As of 2019-06-30 only the Q1 equity (filed 2019-05-01) is
    known; the year-end value (filed 2020-02-01) must be invisible."""
    parsed = sf._parse_companyfacts(_companyfacts_fixture())
    fp = sf.latest_instant(parsed, "equity", date(2019, 6, 30))
    assert fp is not None
    assert fp.end == "2019-03-31"
    assert fp.val == 500_000
    # Later as-of sees the year-end value once it's been filed.
    fp2 = sf.latest_instant(parsed, "equity", date(2020, 3, 1))
    assert fp2.end == "2019-12-31"
    assert fp2.val == 550_000


def test_ttm_flow_sums_four_quarters_when_available():
    """As of 2020-03-01 all four 2019 quarters are filed → TTM = sum."""
    parsed = sf._parse_companyfacts(_companyfacts_fixture())
    ttm = sf.ttm_flow(parsed, "revenue", date(2020, 3, 1))
    assert ttm == 30_000 + 31_000 + 32_000 + 33_000  # 126_000


def test_ttm_flow_falls_back_to_annual_when_quarters_incomplete():
    """As of 2019-06-30 only Q1-2019 is filed (1 quarter) → can't make
    a 4-quarter TTM, so it falls back to the latest filed annual
    (FY2018, 100_000)."""
    parsed = sf._parse_companyfacts(_companyfacts_fixture())
    ttm = sf.ttm_flow(parsed, "revenue", date(2019, 6, 30))
    assert ttm == 100_000


def test_ttm_flow_none_before_any_filing():
    parsed = sf._parse_companyfacts(_companyfacts_fixture())
    assert sf.ttm_flow(parsed, "revenue", date(2017, 1, 1)) is None


def test_facts_as_of_snapshot_shape():
    parsed = sf._parse_companyfacts(_companyfacts_fixture())
    snap = sf.facts_as_of(parsed, date(2020, 3, 1))
    assert snap["revenue"] == 126_000          # TTM flow
    assert snap["equity"] == 550_000           # latest instant
    # Concepts with no data resolve to None, not KeyError.
    assert snap["capex"] is None


def test_earliest_filed_wins_on_duplicate_fact():
    """If the same (end,val) is reported twice (original + amendment),
    keep the EARLIEST filed date — the honest PIT moment."""
    raw = {
        "facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
            {"end": "2020-12-31", "start": "2020-01-01", "val": 9_000,
             "filed": "2021-02-01", "form": "10-K"},
            {"end": "2020-12-31", "start": "2020-01-01", "val": 9_000,
             "filed": "2021-09-01", "form": "10-K/A"},  # amendment, later
        ]}}}}
    }
    parsed = sf._parse_companyfacts(raw)
    pts = parsed["net_income"]
    assert len(pts) == 1
    assert pts[0].filed == "2021-02-01"


def test_ticker_to_cik_parses_sec_shape(monkeypatch):
    sf.clear_ticker_cik_cache()
    fake = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft"},
    }
    monkeypatch.setattr(sf, "_http_get_json", lambda url: fake)
    assert sf.ticker_to_cik("AAPL") == 320193
    assert sf.ticker_to_cik("MSFT") == 789019
    # Exchange suffix is stripped before lookup.
    assert sf.ticker_to_cik("AAPL.US") == 320193
    # Unknown ticker → None (not KeyError).
    assert sf.ticker_to_cik("NOPE") is None
    sf.clear_ticker_cik_cache()
