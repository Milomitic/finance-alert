"""Pydantic schemas for /api/calendar.

The events list is a discriminated union by `kind`: "earnings" or "macro".
Pydantic v2 picks the right shape from the literal field automatically when
the union is declared `Annotated[..., Field(discriminator="kind")]`.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class EarningsEventOut(BaseModel):
    date: date
    kind: Literal["earnings"] = "earnings"
    ticker: str
    name: str
    eps_estimate: float | None = None
    revenue_estimate: float | None = None
    revenue_reported: float | None = None
    sector: str | None = None
    market_cap: int | None = None
    # Extras used by the right-pane stock list. Optional so older clients /
    # cached responses without these fields still validate.
    forward_pe: float | None = None
    earnings_growth: float | None = None       # YoY EPS growth, fraction
    composite_score: float | None = None       # 0-100 composite score
    risk_tier: Literal["conservative", "moderate", "aggressive"] | None = None
    earnings_when: Literal["pre", "after"] | None = None
    # Phase 3G: post-release reported EPS + surprise vs estimate. Mirrors
    # the MacroEvent's actual_value / surprise_pct so the calendar UI
    # can render a unified "Ultimo / Atteso / Sorpresa" row across both
    # event types.
    eps_reported: float | None = None
    surprise_pct: float | None = None


class ConsensoPeriodoOut(BaseModel):
    """Un periodo dello storico nell'unita' del consenso: la stima del suo
    rilascio (dall'archivio) e il dato. None dove non si sa."""
    periodo: date
    previsto: float | None = None
    attuale: float | None = None


class MacroObservationOut(BaseModel):
    """One historical print, used for the small sparkline in the
    calendar's macro detail panel."""
    date: date
    value: float | None


class MacroEventOut(BaseModel):
    date: date
    kind: Literal["macro"] = "macro"
    label: str
    importance: Literal["high", "medium", "low"]
    # Expanded from US/EU/UK/JP to cover every market the user tracks.
    # Mirror of `services/calendar_macros.Region`. Frontend's
    # `lib/calendarMeta.ts` REGION_LABEL/FLAG/REGION_FLAG_ASSET need
    # to grow with this set or unmapped codes render as raw 2-letter
    # codes with the generic 📅 fallback.
    region: Literal[
        "US", "EU", "EZ", "UK", "GB", "JP", "KR", "CN", "HK", "CH",
        "DE", "FR", "IT", "ES", "NL", "BE", "IE",
    ]
    # Stable id of the underlying MacroSeries — drives the link from a
    # calendar event chip to the dedicated detail page (/macro/:series_id).
    # NULL for events sourced from the hardcoded fallback list (no FRED
    # row exists, no detail page to open). Frontend hides the "Apri
    # dettaglio" link in that case.
    series_id: int | None = None
    # Publishing organization shown in the detail page header. Comes
    # from `MacroSeries.source` (populated by the seed script). NULL
    # for events without a backing series row OR for series the seed
    # hasn't covered yet — frontend renders "—".
    source: str | None = None
    # ISO 4217 currency code derived from `region` in `calendar_service`
    # (US→USD, EZ/DE/FR/...→EUR, UK/GB→GBP, JP→JPY, ...). Surfaced in the
    # detail page header so the user knows which FX a rate-decision event
    # affects without having to mentally map region→currency.
    currency: str | None = None
    # FRED-driven insight fields. Populated when the event came from
    # `macro_release_dates` joined with `macro_observations`; null
    # when the event is from the hardcoded fallback list. The UI
    # renders the prev/change/sparkline only when these are present.
    prev_value: float | None = None
    prev_date: date | None = None     # date of the most-recent prior reading
    prior_value: float | None = None
    prior_date: date | None = None    # date of the reading before that
    change_pct: float | None = None
    unit: str | None = None
    history: list[MacroObservationOut] = []
    # Release time UTC HH:MM ("12:30" = 12:30 UTC = 8:30 ET for US events
    # / 14:30 CET for EU events). None when the schedule is daily without
    # a specific window. The frontend renders it next to the date so the
    # user knows when to watch the print.
    release_time: str | None = None
    # Phase 3G: consensus / actual / surprise (sourced from Forexfactory's
    # free weekly XML feed via `forexfactory_consensus`). None when the
    # event isn't covered by the consensus mapping or the weekly XML
    # doesn't yet have the forecast/actual.
    expected_value: float | None = None
    actual_value: float | None = None
    surprise_pct: float | None = None
    # Attuale e precedente nell'unita' del consenso, e come scriverli: vedi
    # `calendar_service.valori_nel_consenso`. None senza consenso.
    attuale_consenso: float | None = None
    previsto_consenso: float | None = None
    precedente_consenso: float | None = None
    formato_consenso: str | None = None
    # La stima del rilascio mostrato come attuale (dall'archivio dei consensi):
    # «Attuale» si colora contro questa, non contro il previsto del rilascio dopo.
    previsto_attuale: float | None = None
    storico_consenso: list[ConsensoPeriodoOut] = []


CalendarEvent = Annotated[
    EarningsEventOut | MacroEventOut,
    Field(discriminator="kind"),
]


class CalendarOut(BaseModel):
    date_from: date = Field(serialization_alias="from")
    date_to: date = Field(serialization_alias="to")
    events: list[CalendarEvent]

    model_config = {"populate_by_name": True}


class MacroReleaseOut(BaseModel):
    """Single historical release row for the detail page table.

    The Investing-style table shows one row per past release with date,
    actual, expected (when known), and previous. We currently only have
    actual/value reliably from FRED; expected_value comes from
    Forexfactory and is only populated for upcoming/recent releases (no
    historical backfill — the feed is week-of). Older rows therefore
    have `expected = None`, displayed as "—" in the UI.
    """
    # FRED observations identify the reference period. They do not carry the
    # corresponding publication date, so the two fields stay separate and
    # publication_date remains null unless the schedule supplies it directly.
    observation_period: date | None = None
    publication_date: date | None = None
    acquired_at: str | None = None
    period_label: str | None = None  # e.g. "Apr" — derived from observation period
    actual_value: float | None = None
    expected_value: float | None = None
    previous_value: float | None = None  # the reading immediately before this one
    release_time_utc: str | None = None  # "14:30" UTC, when known
    # Variazione sul periodo prima e sull'anno prima: % su un indice o un
    # livello, punti su un tasso (`MacroSeriesDetailOut.unita_variazione`).
    variazione: float | None = None
    variazione_annua: float | None = None
    # Dall'archivio dei consensi: la stima del rilascio di questo periodo e il
    # dato pubblicato, nell'unita' del consenso. None prima che l'archivio esista.
    previsto_consenso: float | None = None
    attuale_consenso: float | None = None
    # La stima e il dato sull'anno, quando la misura principale e' sul periodo.
    previsto_annuo_consenso: float | None = None
    attuale_annuo_consenso: float | None = None
    # Ogni variazione contro la stima della SUA misura: "sopra" | "sotto" |
    # "in_linea", None senza stima (`macro_consenso_service.esiti`).
    esito_periodo: str | None = None
    esito_anno: str | None = None


class ReazioneRilascioOut(BaseModel):
    data: date
    rendimento: float


class MacroAnalisiOut(BaseModel):
    """I numeri della pagina di dettaglio: vedi `macro_analisi_service`.
    Ogni statistica porta il suo campione; None dove i dati non bastano."""
    ultima: float | None = None
    media: float | None = None
    dev_std: float | None = None
    zscore: float | None = None
    percentile: float | None = None
    annualizzata_3m: float | None = None
    serie: int = 0
    n_variazioni: int = 0
    massimo: float | None = None
    massimo_il: date | None = None
    minimo: float | None = None
    minimo_il: date | None = None
    # Lo SPY nei giorni di rilascio contro gli altri, movimento assoluto in %.
    reazione_n: int | None = None
    reazione_rilascio: float | None = None
    reazione_altri: float | None = None
    reazione_ultimi: list[ReazioneRilascioOut] = []
    # La variazione del mese contro il rendimento dello SPY nello stesso mese.
    correlazione_r: float | None = None
    correlazione_n: int | None = None
    correlazione_dal: date | None = None
    correlazione_al: date | None = None


class MacroSeriesDetailOut(BaseModel):
    """Full payload for `GET /api/macro/{series_id}` — the detail page.

    Includes everything the page needs in one round-trip:
      - series metadata (label, region, currency, source, importance, unit, description)
      - the latest release (actual / expected / previous, with surprise)
      - full release history for the chart + table (no truncation; the
        UI applies range filtering client-side)
      - upcoming scheduled release dates (next ~3 publications)
    """
    series_id: int
    fred_series_id: str
    label: str
    region: str
    currency: str | None = None
    importance: Literal["high", "medium", "low"]
    value_kind: str | None = None
    source_scale: str | None = None
    description: str | None = None
    source: str | None = None
    data_acquired_at: str | None = None
    # Latest release — actual/expected/previous in one place.
    latest: MacroReleaseOut | None = None
    # Full release history (newest → oldest in the API for natural
    # iteration; the chart can reverse client-side). One row per known
    # observation. `expected` populated only when a Forexfactory match
    # was available at the time of release.
    history: list[MacroReleaseOut] = []
    # Future scheduled publications (date only, no values yet).
    upcoming: list[date] = []
    # "%" su un indice o un livello, "pp" su un tasso.
    unita_variazione: str = "%"
    formato_consenso: str | None = None
    #: Quale variazione misura il consenso: "periodo" | "anno" | "livello".
    misura_consenso: str = "livello"
    analisi: MacroAnalisiOut | None = None
