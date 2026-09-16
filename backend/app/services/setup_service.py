"""Setup lifecycle: detect → persist → convert or expire.

The conversion bookkeeping here is the honest core of the feature. Setups make
no claim about the market, so they cannot be validated the way a signal is.
What they CAN be measured on is whether they do what they say:

    conversion rate = converted / (converted + expired)
    lead time       = days between first_seen and the detector firing

If the conversion rate is near zero, setups are noise. If `lead_days` trends
to 0, they are not buying any time and the feature has failed on its own terms.
Both come for free from the lifecycle — no market prediction involved — which
is what lets this ship before any study exists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.provenance import SETUP_CONVERSION_VERSION
from app.models import Alert, ScanRun, Stock, StockSetup
from app.models.stock_setup import (
    CONVERSION_LIVE,
    CONVERSION_RECONCILED,
    REASON_AGED,
    REASON_DECAYED,
    REASON_MISLINKED,
    REASON_NO_DATA,
    REASON_STALE,
    STATUS_ACTIVE,
    STATUS_CONVERTED,
    STATUS_EXPIRED,
)
from app.services import ohlcv_service
from app.signals.setups.base import TONE_BEAR, TONE_BULL, TONE_UNDETERMINED, SetupMatch, convenience

# A setup not re-observed for this many days is stale: the conditions decayed
# without firing. Short on purpose — a setup is a "watch this now" object, and
# one kept alive for weeks is just clutter that inflates the active list.
_EXPIRE_AFTER_DAYS = 10

# Absolute ceiling on how long a setup may stay pending, measured from
# `first_seen_at` and independent of re-observation.
#
# WHY THIS IS NEEDED. `_EXPIRE_AFTER_DAYS` above measures staleness from
# `last_seen_at`, which every scan refreshes while the conditions still hold —
# so a setup whose conditions persist never expires at all. Measured on
# 2026-08-26: 1,420 active setups, 715 of them `oversold_reversal`, none of
# which had ever resolved. "Oversold and within 8% of a support" is a state a
# stock can sit in for months, and the row sat there with it.
#
# WHY 28. The lead time of every conversion so far: 26% within 3 days, 32% by
# a week, 82% by 13 days, then 12% and 5.5% in the last two bands. Nothing has
# converted past 27 days — but that figure is CENSORED, because the feature
# itself is only 28 days old and no setup has yet had the chance. So the cap is
# justified by the shape of the decline, not by the empty tail: a setup still
# waiting after four weeks is not providing lead time any more, it is
# describing a condition. Revisit once there is a longer history to read.
_MAX_AGE_DAYS = 28
# Scans run twice a day, so a healthy 10-day window contains ~20. Requiring a
# handful means a brief outage cannot silently retire the whole list.
_MIN_SCANS_BEFORE_EXPIRY = 3


def pending_until(first_seen_at: datetime | None) -> date | None:
    """L'ultimo giorno in cui questo setup puo ancora essere pendente.

    ⚠️ E il TETTO da `first_seen_at`, non la scadenza scorrevole da
    `last_seen_at`. Le due regole chiudono entrambe un setup, ma solo una sta
    ferma: `_EXPIRE_AFTER_DAYS` si sposta in avanti a ogni scansione finche le
    condizioni tengono, quindi non dice quando il setup si risolve — dice
    quanto sopravvive senza essere rivisto, ed e permanentemente a dieci
    giorni da oggi.

    Misurato in produzione il 2026-09-11 su 60 setup in lista: finestra
    scorrevole p50 9g e max 10g, tetto p50 14g e max 27g, con il tetto
    vincolante su 9 righe su 60. Prendere il `min()` delle due sembra
    prudente e coincide quasi sempre con la scorrevole, quindi
    SOTTO-RIPORTEREBBE proprio il caso per cui un consumatore chiede questa
    data: un evento a dodici giorni dentro un setup che ne ha quattordici.

    E un limite superiore, non una previsione: il setup puo convertire o
    decadere prima. Chi lo consuma deve dire «l'evento cade dentro la
    finestra», mai «il setup sara ancora aperto quel giorno».
    """
    if first_seen_at is None:
        return None
    return first_seen_at.date() + timedelta(days=_MAX_AGE_DAYS)


def upsert_setup(
    db: Session,
    *,
    stock_id: int,
    match: SetupMatch,
    technical_composite: float | None = None,
    quality_composite: float | None = None,
    bar_date: date | None = None,
) -> StockSetup | None:
    """Create or refresh the live setup for (stock, detector).

    UPDATES rather than inserts when one already exists: `first_seen_at` must
    keep pointing at the start of the wait, because that is what `lead_days`
    is measured from. Re-inserting would silently reset the very number this
    feature exists to report.

    `bar_date` is the last bar the scan read. It is stamped once, when the
    episode opens, as `first_seen_bar`: conversion requires the event to land on
    a LATER bar, and the scan clock (`first_seen_at`) can read yesterday's bar.
    """
    now = datetime.now(UTC)
    score = convenience(
        match,
        technical_composite=technical_composite,
        quality_composite=quality_composite,
    )
    # ⚠️ Solo l'episodio APERTO. Senza `status`, con piu' episodi per coppia
    # questa `scalar_one_or_none` solleverebbe `MultipleResultsFound` — e la
    # ricerca cercherebbe comunque la cosa sbagliata: un episodio chiuso non e'
    # da aggiornare, e' da lasciare stare.
    row = db.execute(
        select(StockSetup).where(
            StockSetup.stock_id == stock_id,
            StockSetup.detector == match.detector,
            StockSetup.status == STATUS_ACTIVE,
        )
    ).scalar_one_or_none()

    # Emission gate. Without it the first production scan produced 1214 setups
    # over ~1000 stocks — the whole market, not a watchlist. A setup below the
    # bar is not merely hidden: an EXISTING row that decays below it is
    # dropped, so a list that stops deserving attention actually shrinks
    # instead of accumulating forever.
    if score < settings.setup_min_convenience:
        if row is not None:
            # ⚠️ Era `db.delete(row)`: l'episodio spariva, e con lui la prova
            # che quella condizione si fosse mai formata. La lista attiva si
            # accorcia lo stesso — filtra su `status == active` — ma il fatto
            # resta scritto.
            #
            # Resta FUORI dal denominatore del tasso di conversione: un setup
            # ritirato perche' ha smesso di meritare attenzione non ha mai
            # avuto l'occasione di convertire, e contarlo come fallimento
            # misurerebbe il ricambio della shortlist invece del valore del
            # setup. Vedi `conversion_stats`.
            row.status = STATUS_EXPIRED
            row.closed_reason = REASON_DECAYED
            row.resolved_at = now
        return None

    if row is None:
        row = StockSetup(
            stock_id=stock_id,
            detector=match.detector,
            tone=match.tone,
            proximity=match.proximity,
            distance_atr=match.distance_atr,
            convenience=score,
            missing=match.missing,
            factors_json=json.dumps(match.factors),
            annotations_json=json.dumps(match.annotations),
            status=STATUS_ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
            first_seen_bar=bar_date,
        )
        db.add(row)
        return row

    # ⚠️ Qui stava la RIATTIVAZIONE, e non c'e' piu'. Una riga risolta che si
    # riformava veniva riusata azzerando `resolved_at`, `converted_alert_id` e
    # `lead_days`: l'attesa nuova era giusta, ma «il setup convertito a giugno»
    # smetteva di esistere. Ora la ricerca sopra vede i soli episodi APERTI,
    # quindi una condizione che si riforma cade nel ramo `row is None` e apre
    # un episodio nuovo, lasciando intatto quello chiuso (FA-061).
    row.tone = match.tone
    row.proximity = match.proximity
    row.distance_atr = match.distance_atr
    row.convenience = score
    row.missing = match.missing
    row.factors_json = json.dumps(match.factors)
    row.annotations_json = json.dumps(match.annotations)
    row.last_seen_at = now
    return row


def tone_compatible(setup_tone: str | None, event_tone: str | None) -> bool:
    """Un evento puo' convertire un setup solo nel verso che il setup attendeva.

    ⚠️ La conversione non lo controllava, e in produzione 68 conversioni su 334
    erano un setup rialzista chiuso da un segnale ribassista (o viceversa):
    stesso detector, evento opposto. Un setup senza direzione accetta entrambi
    i versi, perche' e' esattamente cio' che dichiara. Un evento senza tono non
    converte niente: non si puo' dire che sia quello atteso.
    """
    if event_tone not in (TONE_BULL, TONE_BEAR):
        return False
    return setup_tone in (TONE_UNDETERMINED, event_tone)


def opening_bar(row: StockSetup) -> date | None:
    """La barra su cui l'episodio si e' aperto.

    `first_seen_bar` dove c'e'; sugli episodi aperti prima che esistesse, la
    data di `first_seen_at`. Il ripiego puo' essere un giorno AVANTI rispetto
    alla barra letta davvero (una scansione del mattino legge la barra di
    ieri), quindi con la regola stretta sotto puo' solo mancare una conversione
    sulla barra successiva, mai inventarne una su una barra precedente.
    """
    if row.first_seen_bar is not None:
        return row.first_seen_bar
    return row.first_seen_at.date() if row.first_seen_at is not None else None


def convert_setups_for_event(
    db: Session,
    alert: Alert,
    *,
    signal_date: date | None,
    tone: str | None,
    price: float | None,
) -> StockSetup | None:
    """Converte l'episodio aperto quando il SUO evento accade.

    Chiamata per ogni rilevazione che supera i cancelli della scansione, sia
    che crei un alert sia che ne aggiorni uno esistente. ⚠️ Prima era chiamata
    solo sull'inserimento, e il ramo che aggiorna l'alert terminava senza
    convertire: in produzione 95 setup restavano attivi con la condizione gia'
    scattata, tutti e 95 passati da quel ramo.

    Tre condizioni, e servono tutte:

    - il detector coincide (la ricerca);
    - il verso e' compatibile (`tone_compatible`);
    - la barra dell'evento e' STRETTAMENTE successiva alla barra d'apertura.
      E' questo che impedisce di collegare un episodio nuovo a una rilevazione
      vecchia solo perche' condividono titolo e detector: un evento sulla barra
      in cui il setup diceva «non ancora» non e' l'evento atteso.

    L'evento (data, prezzo, tono) si scrive sul setup e non cambia piu': l'alert
    puntato da `converted_alert_id` e' un'entita' viva che la scansione continua
    ad aggiornare, e l'esito va misurato dal momento che ha chiuso l'attesa.
    """
    detector = alert.signal_name
    if detector is None or alert.stock_id is None or signal_date is None:
        return None
    row = db.execute(
        select(StockSetup).where(
            StockSetup.stock_id == alert.stock_id,
            StockSetup.detector == detector,
            StockSetup.status == STATUS_ACTIVE,
        )
    ).scalar_one_or_none()
    if row is None or not tone_compatible(row.tone, tone):
        return None
    aperta = opening_bar(row)
    if aperta is None or signal_date <= aperta:
        return None

    now = datetime.now(UTC)
    first = row.first_seen_at
    if first is not None and first.tzinfo is None:
        first = first.replace(tzinfo=UTC)
    row.status = STATUS_CONVERTED
    row.resolved_at = now
    row.converted_alert_id = alert.id
    # L'attesa fino alla RILEVAZIONE: orologio della scansione.
    row.lead_days = max(0, (now - first).days) if first else None
    row.converted_signal_date = signal_date
    row.converted_price = price
    row.converted_tone = tone
    row.conversion_source = CONVERSION_LIVE
    row.conversion_version = SETUP_CONVERSION_VERSION
    # L'anticipo rispetto al MERCATO: barra d'apertura -> barra dell'evento.
    row.bar_lead_days = (signal_date - aperta).days
    logger.info(
        f"[setups] {detector} on stock {alert.stock_id} converted on bar "
        f"{signal_date} after {row.lead_days}d of warning"
    )
    return row


def convert_setups_for_alert(db: Session, alert: Alert) -> StockSetup | None:
    """Converte leggendo l'evento dall'alert stesso. Valido solo quando l'alert
    e' appena nato, cioe' quando i suoi campi SONO l'evento; la scansione usa
    `convert_setups_for_event` con i valori della rilevazione."""
    try:
        tone = (json.loads(alert.snapshot) if alert.snapshot else {}).get("tone")
    except (ValueError, TypeError, AttributeError):
        tone = None
    return convert_setups_for_event(
        db, alert, signal_date=alert.signal_date, tone=tone,
        price=float(alert.trigger_price) if alert.trigger_price is not None else None,
    )


def expire_stale_setups(db: Session, *, today: date | None = None) -> int:
    """Retire live setups whose conditions decayed without firing.

    These are NOT deleted: an expired setup is half of the conversion rate.
    Deleting them would leave only the successes on record and make the
    feature look better than it is.

    GUARDED on scans actually having run. `last_seen_at` only advances when a
    scan re-observes the setup, so a stretch with no successful scan — the app
    down, a crashing job, the OHLCV outage of July 2026 — looks identical to
    "the conditions decayed". Ageing setups out during a pipeline problem
    would inflate the expired count and make the feature look worse than it
    is, which is the mirror image of the failure the no-delete rule prevents.
    """
    cutoff = datetime.combine(
        (today or date.today()) - timedelta(days=_EXPIRE_AFTER_DAYS),
        datetime.min.time(),
        tzinfo=UTC,
    )
    # A setup can only be judged stale if scans have had the chance to
    # re-observe it. Require at least this many successful scans since the
    # cutoff, so a quiet pipeline never ages anything out.
    scans_since = db.execute(
        select(func.count())
        .select_from(ScanRun)
        .where(ScanRun.status == "success", ScanRun.completed_at >= cutoff)
    ).scalar_one()
    if scans_since < _MIN_SCANS_BEFORE_EXPIRY:
        logger.info(
            f"[setups] only {scans_since} successful scans since the cutoff — "
            "skipping expiry so a quiet pipeline is not read as decay"
        )
        return 0

    age_cutoff = datetime.combine(
        (today or date.today()) - timedelta(days=_MAX_AGE_DAYS),
        datetime.min.time(),
        tzinfo=UTC,
    )
    rows = db.execute(
        select(StockSetup).where(StockSetup.status == STATUS_ACTIVE)
    ).scalars().all()
    n_stale = 0
    n_aged = 0
    for row in rows:
        seen = row.last_seen_at
        if seen is not None and seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        first = row.first_seen_at
        if first is not None and first.tzinfo is None:
            first = first.replace(tzinfo=UTC)

        stale = seen is not None and seen < cutoff
        # Aged out while still perfectly valid: the conditions never decayed,
        # they simply never resolved either. Counted separately because the
        # two say different things about the detector — decay is the market
        # moving on, age is a gate that describes a state rather than a lead.
        aged = first is not None and first < age_cutoff

        if stale or aged:
            row.status = STATUS_EXPIRED
            row.resolved_at = datetime.now(UTC)
            # ⚠️ La distinzione era gia' calcolata qui e buttata via: le due
            # ragioni finivano contate separatamente nel log e scritte
            # entrambe come `expired`, quindi a posteriori non si poteva piu'
            # sapere quale. Ora si conserva.
            row.closed_reason = REASON_STALE if stale else REASON_AGED
            if stale:
                n_stale += 1
            else:
                n_aged += 1
    if n_stale or n_aged:
        logger.info(
            f"[setups] expired {n_stale + n_aged} setups "
            f"({n_stale} stale, {n_aged} past the {_MAX_AGE_DAYS}-day ceiling)"
        )
    return n_stale + n_aged


def close_setups_without_data(db: Session) -> int:
    """Chiude i setup aperti su titoli la cui serie prezzi si e' fermata.

    ⚠️ Senza questo passo finirebbero in `expire_stale_setups`, che scriverebbe
    `stale` — «le condizioni si sono sfaldate» — e sarebbe falso nel modo
    peggiore: non sono decadute, e' il titolo che ha smesso di quotare. E
    prima ancora non ci arriverebbero nemmeno subito, perche' finche' la
    scansione li rivaluta sulla barra congelata `last_seen_at` avanza ogni
    giorno e la soglia di decadimento non scatta mai. Li chiude il tetto dei 28
    giorni, come `aged` — un'altra ragione sbagliata — e poi RIAPRONO.

    Misurato in produzione il 2026-09-14: nove setup aperti su dodici titoli
    morti, QUATTRO dei quali in shortlist con convenienza fra 78 e 84, cioe'
    mostrati fra le cose da sorvegliare.

    Conta nel denominatore del tasso di conversione come `stale` e `aged`, non
    come `decayed`: l'occasione di convertire c'era davvero, gliel'ha tolta il
    titolo.
    """
    righe = db.execute(
        select(StockSetup)
        .join(Stock, Stock.id == StockSetup.stock_id)
        .where(StockSetup.status == STATUS_ACTIVE, ohlcv_service.series_stalled_clause())
    ).scalars().all()
    for row in righe:
        row.status = STATUS_EXPIRED
        row.resolved_at = datetime.now(UTC)
        row.closed_reason = REASON_NO_DATA
    if righe:
        logger.info(
            f"[setups] {len(righe)} chiusi per dati mancanti: la serie di quei "
            "titoli non avanza piu', quindi nessuna barra potra' farli scattare"
        )
    return len(righe)


def run_post_scan_bookkeeping(db: Session, *, universe: bool) -> None:
    """Retire decayed setups, then cap each detector. Call once at the end of
    EVERY scan, whatever started it — DICHIARANDO il perimetro.

    ⚠️ `universe` non ha un valore di default, ed e' deliberato: una
    scansione che non dice cosa ha guardato non puo' ottenere il permesso di
    dichiarare scaduto qualcosa per errore di omissione. Un default a True
    darebbe il comportamento pericoloso a chi si dimentica.

    ENTRAMBE le operazioni qui dentro chiedono di aver visto TUTTO:

    - `expire_stale_setups` scrive `closed_reason` = «le condizioni sono
      decadute». Detto di un titolo che la scansione non ha riosservato, e'
      un'affermazione falsa — e dal 2026-09-14 (FA-061) e' PERSISTENTE e
      finisce nel denominatore del tasso di conversione, quindi degrada un
      numero a schermo restando plausibile.
    - `prune_to_top_per_detector` classifica i setup fra loro: una classifica
      trasversale non e' conoscibile finche' l'universo non e' stato valutato,
      come questa stessa funzione dice gia' sull'ordine delle due chiamate.

    E' la forma che il CronJob di parita' ha gia' pagato in un'altra veste:
    uno strumento che risponde su un perimetro diverso da quello che crede.
    Una scansione parziale non perde nulla ad astenersi — la prossima
    completa fa il lavoro, che e' esattamente cio' che il paragrafo qui sotto
    descrive come «bounded».

    This exists because it used to be an inline block in the cron job only, and
    the manual-scan entry point in api/alerts.py ended at `run_tracked_scan`
    without it. The two paths then did different bookkeeping, which is the kind
    of divergence that survives precisely because neither path is wrong on its
    own.

    The consequence was bounded rather than permanent — `expire_stale_setups`
    sweeps the whole table, not just the setups the current scan touched, so a
    manual scan's leftovers were retired by the NEXT cron run. Bounded is still
    not correct: between the two, a setup that has decayed still reads as
    live, and `prune_to_top_per_detector`'s cap is over-subscribed.

    Order matters: expire first, then cap. The per-detector ranking is only
    knowable once the whole universe has been evaluated, and capping before
    expiring would rank decayed setups against live ones.

    Never raises. Bookkeeping must not fail a scan that has already done its
    real work — the caller has committed alerts by this point.
    """
    if not universe:
        logger.info(
            "[setups] scansione parziale — nessuna scadenza e nessun taglio: "
            "non si dichiara decaduto cio' che non si e' guardato"
        )
        return
    try:
        # ⚠️ PRIMA della scadenza, e l'ordine e' la meta' del punto: chi aspetta
        # barre che non arriveranno si prende la propria ragione invece di
        # finire in `stale`, che direbbe una cosa falsa.
        close_setups_without_data(db)
        expire_stale_setups(db)
        prune_to_top_per_detector(db)
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[setups] post-scan bookkeeping failed: {e}")
        db.rollback()


def conversion_stats(db: Session) -> dict:
    """The feature's own report card. Read-only.

    Two layers, and the distinction matters. The FIRST needs no market claim
    at all: how many setups are waiting, how many converted, how many expired,
    how much warning the converted ones gave. Those are facts about the
    feature, true from day one, and they are why this page could ship before
    any study existed.

    The SECOND asks whether a converted setup went on to be right, by
    following `converted_alert_id` into the `signal_outcomes` warehouse. Two
    rules keep it honest:

      - the label is `mkt_neutral_hit`, NEVER `abs_hit`. Absolute hit books
        the market's drift as the setup's merit — on the live warehouse
        `sr_flip` bull reads 57.9% absolute against 51.5% market-neutral.
      - a converted setup with no outcome yet, or with no universe benchmark
        on its trigger date, is PENDING. Folding either into "negativo" would
        invent losses that never happened.
    """
    # ⚠️ TUTTA la popolazione, non i soli setup in shortlist (decisione
    # dell'utente, 2026-09-16). Il filtro precedente — «un setup mai mostrato
    # non ha fatto promesse» — riduceva le misure a 98 righe su 2.267 e a 11
    # convertiti su 334, nessuno dei quali con un esito maturato, mentre fra
    # tutti i convertiti gli esiti maturati erano 83: la pagina diceva «nessun
    # esito» su dati che esistevano. `shortlisted` descrive cosa la lista
    # mostra OGGI, non una proprieta' storica del setup, quindi non e' un
    # perimetro su cui misurare il passato. La shortlist resta il perimetro
    # della LISTA, ed e' riportata a parte (`active_shortlisted`).
    rows = db.execute(select(StockSetup)).scalars().all()
    active = [r for r in rows if r.status == STATUS_ACTIVE]
    converted = [r for r in rows if r.status == STATUS_CONVERTED]
    # ⚠️ Le chiusure per DECADIMENTO restano fuori dal denominatore, e la
    # ragione e' una domanda diversa da quella che il tasso pone. «Quante
    # attese si sono trasformate in un segnale» si misura sulle attese che
    # l'occasione l'hanno avuta: un setup ritirato perche' ha smesso di
    # meritare attenzione non ha mai potuto convertire, e contarlo come
    # fallimento misurerebbe il ricambio della shortlist.
    #
    # Prima della migrazione FA-061 quelle righe venivano CANCELLATE, quindi il
    # tasso gia' non le contava: escluderle tiene fermo il numero a schermo
    # (9/18 = 50,0% in produzione) mentre la storia smette di andare persa. La
    # domanda «un setup decaduto e' una mancata conversione?» diventa cosi'
    # rispondibile, invece di essere decisa di nascosto da un DELETE.
    decayed = [r for r in rows
               if r.status == STATUS_EXPIRED and r.closed_reason == REASON_DECAYED]
    # ⚠️ Chiusi da una conversione di verso opposto: fuori dal tasso come i
    # ritirati, per la stessa ragione — l'occasione di convertire gliel'ha tolta
    # un errore nostro, non il mercato.
    mislinked = [r for r in rows
                 if r.status == STATUS_EXPIRED and r.closed_reason == REASON_MISLINKED]
    expired = [r for r in rows
               if r.status == STATUS_EXPIRED
               and r.closed_reason not in (REASON_DECAYED, REASON_MISLINKED)]
    resolved = len(converted) + len(expired)
    leads = sorted(r.lead_days for r in converted if r.lead_days is not None)
    bar_leads = sorted(r.bar_lead_days for r in converted if r.bar_lead_days is not None)

    # ⚠️ L'esito si legge dal SETUP, cioe' dall'evento che l'ha convertito, non
    # dall'alert puntato: l'alert puo' aver spostato la sua data dopo la
    # conversione, e il suo esito misurerebbe un altro momento.
    outcomes = _event_outcomes(converted)
    positive = sum(1 for o in outcomes.values() if o.mkt_neutral_hit == 1)
    negative = sum(1 for o in outcomes.values() if o.mkt_neutral_hit == 0)
    unavailable = _outcome_unavailable(db, converted, outcomes)

    returns = _return_summary(list(outcomes.values()))
    # Il termine di paragone del tasso: quanto spesso lo stesso segnale scatta
    # su un titolo qualsiasi in 28 giorni. Senza, «48%» si legge nel vuoto.
    from app.services.setup_base_rate import base_firing_rates

    nel_tasso = converted + expired
    aperture = [r.first_seen_at for r in nel_tasso if r.first_seen_at is not None]
    base = base_firing_rates(db, min(aperture).date()) if aperture else None
    by_detector = _per_detector(converted, expired, outcomes, base)
    base_pct, base_lift = _aggregate_base(by_detector, len(converted), resolved)

    return {
        # Il perimetro resta dichiarato nel payload: tutti i setup registrati.
        "scope": "all",
        "active": len(active),
        # Quanti degli attivi sono in lista adesso: il perimetro della LISTA,
        # distinto da quello delle misure e riportato come tale.
        "active_shortlisted": sum(1 for r in active if r.shortlisted),
        #: Chiusi per decadimento: FUORI dal denominatore ma NON invisibili.
        #: Escluderli senza mostrarli sarebbe indistinguibile dal cancellarli,
        #: che e' cio' che si e' appena smesso di fare.
        "decayed": len(decayed),
        "mislinked": len(mislinked),
        "converted": len(converted),
        "expired": len(expired),
        #: TUTTI gli episodi chiusi, qualunque la ragione: e' il totale della
        #: vista Esiti. `closed` qui sotto e' un'altra cosa — il denominatore
        #: del tasso — e a schermo i due numeri vanno nominati diversamente.
        "closed_total": resolved + len(decayed) + len(mislinked),
        "excluded_from_rate": len(decayed) + len(mislinked),
        #: Chiusi prima che la ragione fosse registrata (FA-061). Restano nel
        #: tasso — erano scadenze vere — ma la lacuna resta a schermo.
        "closed_without_reason": sum(1 for r in expired if r.closed_reason is None),
        # The two tabs, each with its own total, and the sum of everything the
        # feature has ever tracked.
        "closed": resolved,
        "total": len(rows),
        # ⚠️ Le tre voci devono SOMMARE ad `active`. Finche' i toni erano due
        # la terza non esisteva e la somma tornava per caso; da quando
        # `squeeze_expansion` dichiara di non conoscere il verso, mostrare
        # solo rialzisti e ribassisti lascerebbe un resto senza nome sotto un
        # totale che non torna — e chi legge non avrebbe modo di sapere
        # dov'e' finito.
        "active_bull": sum(1 for r in active if r.tone == TONE_BULL),
        "active_bear": sum(1 for r in active if r.tone == TONE_BEAR),
        "active_undetermined": sum(1 for r in active if r.tone == TONE_UNDETERMINED),
        # None (not 0.0) while nothing has resolved yet: a rate computed over
        # an empty denominator is not "0%", it is "unknown", and showing 0%
        # would read as "setups never work".
        "conversion_rate": round(len(converted) / resolved, 3) if resolved else None,
        # Everything converted that is neither a hit nor a miss: horizon not
        # elapsed, or no universe benchmark on the day. Absent, not failed.
        "converted_positive": positive,
        "converted_negative": negative,
        # Judgeable but not judged yet: horizon still running, or a day
        # without universe benchmark. Never folded into "negativo".
        "converted_pending": len(converted) - positive - negative - unavailable,
        #: Convertiti il cui esito NON potra' mai essere misurato: riconciliati
        #: (la prima rilevazione non fu registrata) o storici il cui alert ha
        #: spostato la data oltre la conversione. Contati a parte, mai confusi
        #: con quelli in attesa.
        "converted_outcome_unavailable": unavailable,
        # Efficacy as a RATE, with everything needed to disbelieve it. The
        # counts above already say 7 and 3; a bare "70%" would not.
        **returns,
        "by_detector": by_detector,
        "avg_lead_days": round(sum(leads) / len(leads), 1) if leads else None,
        # The median and the range beside the mean: one number cannot say
        # whether the warning was reliably a week or anywhere from a day to a
        # month, and the wait is the whole product.
        "median_lead_days": _median_of(leads),
        "lead_days_min": leads[0] if leads else None,
        "lead_days_max": leads[-1] if leads else None,
        #: L'anticipo rispetto al MERCATO (barra d'apertura -> barra
        #: dell'evento), solo dove l'evento e' registrato. `median_lead_days`
        #: sopra e' l'attesa fino alla RILEVAZIONE.
        #: Quota di titoli qualsiasi su cui lo stesso segnale scatta in una
        #: finestra da 28 giorni, pesata per tipo e verso dei setup chiusi nel
        #: tasso. `base_lift` = tasso di conversione / tasso di base. Null
        #: finche' non esiste una finestra completa. Vedi `setup_base_rate`.
        "base_rate_pct": base_pct,
        "base_lift": base_lift,
        "base_windows": base.windows if base else 0,
        "base_window_days": 28,
        "median_bar_lead_days": _median_of(bar_leads),
        "bar_lead_days_n": len(bar_leads),
        #: Quante conversioni per versione delle regole. `null` = storico, la
        #: regola di allora non e' registrata: e' la popolazione di prima.
        "conversion_versions": _version_counts(r.conversion_version for r in converted),
    }


def prune_to_top_per_detector(db: Session) -> int:
    """Keep only the strongest N active setups per (detector, tone).

    The floor alone leaves the list lopsided: `squeeze_expansion` matched 291
    names on the first real scan, because ~30% of any universe has compressed
    bands at any moment. Without a cap one common pattern buries the rarer,
    more specific ones — and the rare ones are the reason to look.

    Runs AFTER the scan because the ranking is only knowable once every stock
    has been evaluated.

    Dropped rows are FLAGGED, never deleted. Deleting them looked tidy and was
    a bug: `first_seen_at` would go with them, so a setup hovering at the cap
    boundary would restart its wait each time it re-entered, quietly zeroing
    `lead_days` — the one number this feature is judged by. The row survives,
    keeps its history, and simply stops being surfaced.
    """
    rows = db.execute(
        select(StockSetup).where(StockSetup.status == STATUS_ACTIVE)
    ).scalars().all()
    by_group: dict[tuple[str, str], list[StockSetup]] = {}
    for r in rows:
        by_group.setdefault((r.detector, r.tone), []).append(r)

    dropped = 0
    for group in by_group.values():
        group.sort(key=lambda r: r.convenience, reverse=True)
        for rank, r in enumerate(group):
            keep = rank < settings.setup_max_per_detector
            if r.shortlisted != keep:
                r.shortlisted = keep
                if not keep:
                    dropped += 1
    if dropped:
        logger.info(f"[setups] {dropped} dropped out of the per-detector shortlist")
    return dropped


@dataclass(frozen=True)
class EventOutcome:
    """L'esito dell'evento di conversione, nella forma che `_return_summary`
    legge. Costruito dalle colonne del setup, non da `signal_outcomes`."""
    mkt_neutral_hit: int | None
    mkt_neutral_excess: float | None
    fwd_return: float | None
    horizon_days: int | None
    signal_date: date


def _event_outcomes(converted: list[StockSetup]) -> dict[int, EventOutcome]:
    """{setup_id: esito} per i convertiti il cui evento e' maturato."""
    return {
        r.id: EventOutcome(
            mkt_neutral_hit=r.outcome_mkt_neutral_hit,
            mkt_neutral_excess=r.outcome_mkt_neutral_excess,
            fwd_return=r.outcome_fwd_return,
            horizon_days=r.outcome_horizon_days,
            signal_date=r.outcome_signal_date,
        )
        for r in converted
        if r.outcome_matured_at is not None and r.outcome_signal_date is not None
    }


def _outcome_unavailable(
    db: Session, converted: list[StockSetup], outcomes: dict[int, EventOutcome]
) -> int:
    """Quanti convertiti non avranno MAI un esito misurabile.

    Riconciliati: la data dell'evento non esiste. Storici senza data d'evento:
    solo se l'alert ha GIA' spostato la sua data oltre il giorno della
    conversione, perche' l'esito del magazzino misurerebbe un momento
    successivo e `signal_outcome_service.mature_setup_outcomes` non lo accetta.
    """
    n = sum(1 for r in converted if r.conversion_source == CONVERSION_RECONCILED)
    undated = [
        r for r in converted
        if r.id not in outcomes
        and r.conversion_source != CONVERSION_RECONCILED
        and r.converted_signal_date is None
        and r.converted_alert_id is not None
        and r.resolved_at is not None
    ]
    if not undated:
        return n
    dates = dict(db.execute(
        select(Alert.id, Alert.signal_date)
        .where(Alert.id.in_([r.converted_alert_id for r in undated]))
    ).all())
    for r in undated:
        sd = dates.get(r.converted_alert_id)
        if sd is None or sd > r.resolved_at.date():
            n += 1
    return n


def _version_counts(versions) -> dict[str, int]:
    """{versione: conteggio}, con lo storico sotto una chiave che lo DICE."""
    out: dict[str, int] = {}
    for v in versions:
        k = v or "non registrata"
        out[k] = out.get(k, 0) + 1
    return out


def _pct(x: float | None) -> float | None:
    return None if x is None else round(x * 100.0, 2)


def _median_of(xs: list[float]) -> float | None:
    """La mediana, ORDINANDO da sola. Proprietario unico.

    ⚠️ Ne esisteva una seconda copia annidata dentro `conversion_stats`, e non
    era un duplicato: NON ordinava. Funzionava perche' il chiamante passava
    `leads` gia' ordinata venti righe sopra — cioe' la sua correttezza
    dipendeva da cosa faceva qualcun altro, e niente lo diceva. Su un elenco
    non ordinato le due rispondevano 30 contro 7.

    ⚠️ E `float(...)`: l'annotazione diceva `float | None` mentre nel caso
    DISPARI restituiva l'int ricevuto. Un'annotazione vera meta' delle volte e'
    peggio di nessuna annotazione, perche' chi legge smette di controllare."""
    if not xs:
        return None
    ys = sorted(xs)
    mid = len(ys) // 2
    return float(ys[mid] if len(ys) % 2 else (ys[mid - 1] + ys[mid]) / 2.0)


def _return_summary(outcomes: list[EventOutcome]) -> dict:
    """What a converted setup was WORTH, not just whether it was right.

    Two return series side by side, deliberately. `mkt_neutral_excess` is the
    honest one — it strips the market drift a bull-tone setup would collect for
    free — and `fwd_return` is what the stock actually did. CLAUDE.md's worked
    example is `high52_momentum` at 54.0 absolute against 50.5 market-neutral,
    where 3.5 of the 4 points above a coin flip were simply being long. One
    number alone lets that hide; the pair makes it visible.

    The MEDIAN leads because forward returns are right-skewed: a single
    multi-bagger drags a mean upward and would describe a typical setup that
    does not exist. The mean is kept beside it precisely so the gap shows.

    The interval comes from `independent_blocks` + `sized_interval`, the same
    treatment every other efficacy number in this repo gets: setups that fire
    days apart share most of their forward window, so the row count is not the
    sample size.
    """
    from app.services.detector_performance_service import (
        _DEFAULT_MIN_N,
        independent_blocks,
        sized_interval,
    )

    judged = [o for o in outcomes if o.mkt_neutral_hit is not None]
    excess = [o.mkt_neutral_excess for o in judged if o.mkt_neutral_excess is not None]
    absolute = [o.fwd_return for o in outcomes if o.fwd_return is not None]

    n = len(judged)
    hits = sum(1 for o in judged if o.mkt_neutral_hit == 1)
    rate = round(hits / n * 100.0, 1) if n else None

    horizon = max((o.horizon_days for o in judged), default=None)
    eff_n = (
        independent_blocks([o.signal_date for o in judged], horizon)
        if n and horizon
        else 0
    )
    ci = sized_interval(rate_pct=rate, effective_n=eff_n) if rate is not None and eff_n else None

    return {
        "converted_judged": n,
        # Percent, market-neutral. The counts are already exposed separately;
        # this is the same fact in the form a person compares against 50.
        "converted_hit_rate": rate,
        "converted_effective_n": eff_n,
        "converted_horizon_days": horizon,
        "converted_ci_low": ci[0] if ci else None,
        "converted_ci_high": ci[1] if ci else None,
        # Thin evidence is FLAGGED, never hidden: a rate the reader cannot see
        # is worse than one they can distrust.
        "converted_low_confidence": eff_n < _DEFAULT_MIN_N,
        "median_excess_pct": _pct(_median_of([float(x) for x in excess])),
        "mean_excess_pct": _pct(
            sum(float(x) for x in excess) / len(excess) if excess else None
        ),
        "median_return_pct": _pct(_median_of([float(x) for x in absolute])),
        "mean_return_pct": _pct(
            sum(float(x) for x in absolute) / len(absolute) if absolute else None
        ),
    }


def _aggregate_base(rows: list[dict], converted: int, resolved: int) -> tuple[float | None, float | None]:
    """Il tasso di base dell'intera funzione, pesato sui setup chiusi di ogni
    tipo — lo stesso peso che ogni tipo ha nel tasso di conversione aggregato.

    Solo i tipi con un tasso di base contano, al numeratore E al denominatore:
    un tipo senza paragone non deve abbassare il tasso di base facendo finta di
    valere zero."""
    pesati = [(r["resolved"], r["base_rate_pct"]) for r in rows if r["base_rate_pct"] is not None]
    peso = sum(n for n, _ in pesati)
    if not peso or not resolved:
        return None, None
    base = sum(n * b for n, b in pesati) / peso
    rate = converted / resolved * 100.0
    return round(base, 1), (round(rate / base, 1) if base > 0 else None)


def _per_detector(
    converted: list[StockSetup],
    expired: list[StockSetup],
    outcomes: dict[int, EventOutcome],
    base: object | None = None,
) -> list[dict]:
    """One row per setup detector: does THIS setup convert, and is it worth it.

    The aggregate answers "does the feature work". It cannot answer "which
    setup should I trust", and averaging a detector that converts nine times
    out of ten with one that never converts hides both.

    Every row carries its own denominators. A detector with two resolved
    setups gets a conversion rate of 50% that means nothing, so `resolved` and
    `judged` travel beside every rate rather than in a tooltip.
    """
    from app.services.detector_performance_service import (
        _DEFAULT_MIN_N,
        independent_blocks,
        sized_interval,
    )

    names = sorted({r.detector for r in converted} | {r.detector for r in expired})

    rows: list[dict] = []
    for name in names:
        conv = [r for r in converted if r.detector == name]
        exp = [r for r in expired if r.detector == name]
        resolved = len(conv) + len(exp)

        mine = [outcomes[r.id] for r in conv if r.id in outcomes]
        judged = [o for o in mine if o.mkt_neutral_hit is not None]
        hits = sum(1 for o in judged if o.mkt_neutral_hit == 1)
        rate = round(hits / len(judged) * 100.0, 1) if judged else None

        horizon = max((o.horizon_days for o in judged), default=None)
        eff_n = (
            independent_blocks([o.signal_date for o in judged], horizon)
            if judged and horizon
            else 0
        )
        ci = sized_interval(rate_pct=rate, effective_n=eff_n) if rate is not None and eff_n else None
        excess = [
            float(o.mkt_neutral_excess) for o in judged if o.mkt_neutral_excess is not None
        ]

        conversion_rate = round(len(conv) / resolved * 100.0, 1) if resolved else None
        toni: dict[str, int] = {}
        for r in conv + exp:
            toni[r.tone] = toni.get(r.tone, 0) + 1
        base_frac = base.for_tone_mix(name, toni) if base is not None else None
        base_pct = round(base_frac * 100.0, 1) if base_frac is not None else None

        rows.append({
            "detector": name,
            "converted": len(conv),
            "expired": len(exp),
            "resolved": resolved,
            "conversion_rate": conversion_rate,
            # Quanto spesso lo stesso segnale, negli stessi versi, scatta su un
            # titolo qualsiasi in 28 giorni; e quante volte piu' spesso scatta
            # dopo un setup.
            "base_rate_pct": base_pct,
            "lift": (
                round(conversion_rate / base_pct, 1)
                if conversion_rate is not None and base_pct else None
            ),
            "judged": len(judged),
            "positive": hits,
            "negative": len(judged) - hits,
            "hit_rate": rate,
            "effective_n": eff_n,
            "horizon_days": horizon,
            "ci_low": ci[0] if ci else None,
            "ci_high": ci[1] if ci else None,
            "low_confidence": eff_n < _DEFAULT_MIN_N,
            "median_excess_pct": _pct(_median_of(excess)),
        })

    # Most-resolved first: the rows with something to say lead, and a detector
    # with one setup does not sit above one with forty because it got lucky.
    rows.sort(key=lambda r: (-r["resolved"], r["detector"]))
    return rows
