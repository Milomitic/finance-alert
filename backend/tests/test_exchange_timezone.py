"""exchange_timezone: the single source of truth the frontend reads off the
stock-detail response (was a hand-mirrored map on the client)."""
from app.services.live_quote_service import exchange_timezone


def test_us_listings_default_to_new_york():
    assert exchange_timezone("AAPL") == "America/New_York"
    assert exchange_timezone("BRK-B") == "America/New_York"


def test_known_suffixes_map_to_their_zone():
    assert exchange_timezone("HSBA.L") == "Europe/London"
    assert exchange_timezone("ENEL.MI") == "Europe/Berlin"
    assert exchange_timezone("0700.HK") == "Asia/Hong_Kong"
    assert exchange_timezone("000300.SS") == "Asia/Shanghai"
    assert exchange_timezone("7203.T") == "Asia/Tokyo"
    assert exchange_timezone("EQNR.OL") == "Europe/Oslo"
    assert exchange_timezone("BHP.AX") == "Australia/Sydney"


def test_unknown_suffix_falls_back_to_us():
    assert exchange_timezone("FOO.ZZ") == "America/New_York"
