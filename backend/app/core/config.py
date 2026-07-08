"""Application configuration loaded from environment / .env."""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    secret_key: str = Field(default="")
    session_cookie_name: str = "finance_alert_session"
    session_max_age_days: int = 7
    log_level: str = "INFO"
    admin_username: str = "admin"
    admin_password_hash: str = ""
    # Throttling login (B4-11, light): dopo N fallimenti consecutivi per uno
    # username il login risponde 429 + Retry-After finché non passano
    # `login_lockout_seconds` dall'ultimo fallimento (finestra sliding).
    # Stato in-memory: si azzera al riavvio del backend, by design
    # (local-first, processo singolo). Vedi services/login_throttle.py.
    login_max_failed_attempts: int = 5
    login_lockout_seconds: int = 60
    public_base_url: str = "http://localhost:8000"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_delivery_mode: str = "digest"  # only "digest" implemented in Fase 2
    # Push Telegram istantaneo per-segnale (oltre al digest giornaliero).
    # OFF di default: quando ON, a fine scan viene inviato UN messaggio
    # compatto con i segnali della scansione la cui Forza (snapshot
    # strength) >= telegram_push_min_strength. Vedi
    # notifier_service.notify_signal_alerts.
    telegram_push_per_signal: bool = False
    telegram_push_min_strength: int = 75
    # Notifiche Telegram di SALUTE piattaforma (audit 2026-07-08: i cron 13F
    # sono rimasti morti per mesi senza che nulla lo segnalasse). ON di
    # default: (a) push quando uno scan termina 'failed' (crash, non cancel
    # utente), (b) push quando il rollup di salute TRANSITA verso
    # degraded/outage (solo al cambio di stato, max 1 ogni 6h per stato —
    # vedi health_rollup.maybe_notify_transition). Richiede comunque
    # telegram_bot_token + telegram_chat_id configurati.
    telegram_notify_health: bool = True
    digest_hour: int = 8
    digest_minute: int = 0
    scan_hour: int = 23
    scan_minute: int = 30
    # Extra weekday scan tick (besides the nightly one) so a pattern that
    # completes at a market close is detected the same evening WHILE the app
    # is open — not only at the 23:30 tick. After the EU close (~17:30 CET).
    scan_hour_2: int = 18
    scan_minute_2: int = 30
    # Local-first catch-up: this is a desktop app, so the in-process cron only
    # fires while the backend is actually running — overnight/off-hours ticks
    # are silently missed, and signals then surface days late (only on the
    # user's next manual scan). On boot, if the last successful scan is older
    # than this many hours, auto-run a scan so opening the app detects the
    # signals from the days the machine was off. 0 disables.
    scan_startup_stale_hours: int = 16
    # Live universe-wide top-movers sweep (dashboard 1G). The board's live
    # re-rank only polls a bounded candidate pool, so a genuine intraday mover
    # that wasn't an EOD mover is invisible. A ROTATING sweep stages live
    # change% for the whole universe a chunk at a time — gentle on yfinance:
    # only open-market tickers are fetched, `chunk` names per `seconds` tick,
    # full coverage in ~(universe/chunk × seconds). Entries expire after
    # `stale_seconds`. 0 seconds disables the sweep.
    live_movers_sweep_seconds: int = 75
    live_movers_chunk: int = 200
    live_movers_stale_seconds: int = 900   # 15 min
    # Top-N gainers + N losers surfaced from the sweep. 30+30=60 leaves room
    # under the FE's 120-ticker candidate cap for the EOD lists too (so the
    # board mixes the true live universe movers with the familiar EOD names).
    live_movers_top_n: int = 30
    # Signal engine: minimum confidence (0-100) for a detected signal to
    # become an alert. Below this the signal is computed but not surfaced.
    signal_min_confidence: int = 60
    # Signal engine recency guard: a detected signal is only surfaced if its
    # signal_date is within this many calendar days of the latest OHLCV bar.
    # Stops the first scan after a deploy/backfill from flooding the feed with
    # months-old setups (the ~260-bar window contains a year of history).
    signal_max_age_days: int = 7
    # Dedup cooldown: a "state" detector (trend_pullback, sr_flip, oversold,
    # high52, structure_break, chart_pattern, adx_confirmation, volume_breakout)
    # stamps signal_date on the LATEST bar, so the same ongoing setup would mint
    # a new (stock, name, signal_date) every day the condition holds -> a stream
    # of near-duplicate alerts differing only in price. Within this many days of
    # an existing same-(stock, signal, direction) alert we treat the detection
    # as the SAME setup: refresh the live alert in place (or respect an archive)
    # instead of inserting a duplicate. The anchor moves forward on each refresh,
    # so an indefinitely-persistent setup stays a single living alert.
    signal_dedup_cooldown_days: int = 14
    # Chain lifetime cap: a PERSISTENT condition re-arms the dedup cooldown on
    # every scan, so a living alert could refresh forever and never leave the
    # confluence window. Once (signal_date - first_emitted_at) exceeds this many
    # days the chain dies: the refresh stops (no amend, no new row) and a fresh
    # alert is only inserted when the detector re-fires OUTSIDE the cooldown of
    # the now-frozen anchor. 28d = two cooldown windows — long enough for a real
    # multi-week setup, short enough that "always on" conditions stop looping.
    signal_chain_max_age_days: int = 28
    # Auto-archive concluded signals at scan end: alerts whose outcome row has
    # matured AND whose signal_date has left the confluence window
    # (signal_max_age_days) are archived in one UPDATE, so the active feed only
    # shows setups that are still actionable. The rows stay queryable via the
    # "Solo archiviati" filter; flip to False to keep concluded alerts active.
    auto_archive_concluded: bool = True
    # Quality gates to cut false positives (both default ON; override in .env).
    # Regime gate: drop trend-following signals whose direction contradicts the
    # prevailing EMA200-slope trend (reversal/fundamental detectors are exempt).
    signal_require_trend_alignment: bool = True
    # Follow-through: require the bar after the trigger to hold the invalidation
    # level; a fresh last-bar trigger is held until a later scan can confirm it.
    signal_require_follow_through: bool = True
    # Weight of the (non-monotonic) trend-maturity factor in trend-following
    # detectors. 0 disables it. Backtest-tuned; see technical-evaluation docs.
    signal_trend_maturity_weight: float = 0.6
    # FRED (Federal Reserve Economic Data) API key for the macro
    # calendar. Free, gettable from https://fred.stlouisfed.org —
    # rate-limited at 120 req/min. Empty string disables FRED-driven
    # macro events; the calendar then renders only the hardcoded
    # fallback list in `services/calendar_macros.py`.
    fred_api_key: str = ""
    # Finnhub API key — used as a low-latency fallback source for
    # earnings actuals (epsActual / revenueActual) when yfinance hasn't
    # yet scraped the press release. Free tier from https://finnhub.io
    # gives 60 req/min, ample for our ~1100-stock catalog when we only
    # poll the "imminent earnings" subset (~5-20 stocks per refresh).
    # Empty string disables the Finnhub fallback; yfinance remains the
    # sole source for earnings.
    finnhub_api_key: str = ""
    # Marketaux API key — used as a fallback news source when yfinance returns
    # 0 headlines for a ticker. Free tier from https://www.marketaux.com gives
    # 100 req/day, sufficient for a single-user local-first context.
    # Empty string disables the fallback; yfinance remains the sole source.
    marketaux_api_key: str = ""
    # Twelve Data API key — TIER-3 fallback for EPS actuals, behind
    # yfinance (primary) and Finnhub (fallback #1). A SEPARATE provider
    # from Finnhub, so a Finnhub rate-limit/outage no longer leaves a
    # freshly-released EPS actual unfilled. Free tier from
    # https://twelvedata.com gives 800 req/day, 8 req/min — ample since
    # only the narrow "actual just lagging" subset hits it. Note: the
    # free /earnings endpoint is EPS-only (no revenue). Empty string
    # disables this tier; yfinance + Finnhub remain the sources.
    twelvedata_api_key: str = ""

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()


def ensure_data_dir() -> None:
    """Make sure ./data and ./data/logs exist."""
    Path("./data").mkdir(parents=True, exist_ok=True)
    Path("./data/logs").mkdir(parents=True, exist_ok=True)
