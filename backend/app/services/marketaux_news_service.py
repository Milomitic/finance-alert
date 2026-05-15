"""Marketaux news API — secondario per il fallback in stock_news_service.

Free tier: 100 req/giorno, payload ridotto. Sufficient per single-user
local-first context (max ~50 ticker visualizzati al giorno).

Schema risposta: https://www.marketaux.com/docs/api
Solo i campi che ci servono vengono mappati su NewsItem (riusiamo il
modello di stock_news_service per coerenza).
"""
import re
from dataclasses import dataclass

import requests
from loguru import logger

from app.core.config import settings
from app.core.errors import UpstreamUnavailable

# Used to scrub the api_token from any error response body we log.
# Marketaux sometimes echoes the token in JSON error messages.
_API_TOKEN_PATTERN = re.compile(
    r'(api[-_]?token["\']?\s*[:=]\s*["\']?)[^"\'&\s,}]+', re.IGNORECASE
)


def _scrub_token(text: str) -> str:
    """Return `text` with any api_token=... or "api_token":"..." substring
    redacted. Used before logging Marketaux error bodies."""
    return _API_TOKEN_PATTERN.sub(r'\1[REDACTED]', text)


@dataclass
class NewsItem:
    title: str
    url: str
    published_at: str
    source: str


_BASE = "https://api.marketaux.com/v1/news/all"
_TIMEOUT = 8.0


def fetch_news(ticker: str, limit: int = 10) -> list[NewsItem]:
    """Ritorna headline per `ticker`. Lista vuota se la chiave non è configurata
    (graceful degrade — il caller decide se sollevare o ignorare)."""
    if not settings.marketaux_api_key:
        return []
    try:
        resp = requests.get(
            _BASE,
            params={
                "api_token": settings.marketaux_api_key,
                "symbols": ticker,
                "limit": limit,
                "language": "en",
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        raise UpstreamUnavailable(str(e), source="marketaux", op="news") from e

    if resp.status_code != 200:
        logger.warning(
            f"[marketaux] HTTP {resp.status_code} for {ticker}: "
            f"{_scrub_token(resp.text[:200])}"
        )
        raise UpstreamUnavailable(
            f"marketaux HTTP {resp.status_code}", source="marketaux", op="news"
        )
    data = resp.json().get("data", [])
    return [
        NewsItem(
            title=item.get("title", ""),
            url=item.get("url", ""),
            published_at=item.get("published_at", ""),
            source=item.get("source", ""),
        )
        for item in data
    ]
