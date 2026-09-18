"""La maturazione: dagli alert e dalle barre alle righe di `plan_outcomes`.

Gira a fine scansione, best-effort, come la maturazione del magazzino degli
esiti a orizzonte fisso — e come quella non deve mai rompere la scansione.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, PlanOutcome, Stock
from app.services.plan_outcome_service import mature_plan_outcomes


def _titolo(db: Session, ticker: str = "AAA") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Corp", country="US")
    db.add(s)
    db.flush()
    return s


def _barre(db: Session, stock: Stock, righe: list[tuple[str, float, float, float]]) -> None:
    for d, hi, lo, cl in righe:
        db.add(OhlcvDaily(stock_id=stock.id, date=date.fromisoformat(d),
                          open=cl, high=hi, low=lo, close=cl, volume=1000))
    db.flush()


def _alert(db: Session, stock: Stock, *, detector: str = "sr_flip",
           scattato: str = "2026-03-02", prezzo: float = 100.0,
           invalidazione: float | None = 96.0, tono: str = "bull",
           orizzonte: str = "short") -> Alert:
    snap: dict = {"tone": tono, "atr": 2.0, "horizon": orizzonte, "chain": []}
    if invalidazione is not None:
        snap["invalidation"] = {"level": invalidazione, "reason": "prova"}
    a = Alert(stock_id=stock.id, signal_name=detector,
              signal_date=date.fromisoformat(scattato) - timedelta(days=1),
              triggered_at=datetime.fromisoformat(scattato).replace(tzinfo=UTC),
              trigger_price=prezzo, snapshot=json.dumps(snap))
    db.add(a)
    db.flush()
    return a


# ─── 1. Il caso nominale ───────────────────────────────────────────────────

def test_un_piano_risolto_produce_una_riga(db: Session) -> None:
    s = _titolo(db)
    a = _alert(db, s)
    _barre(db, s, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 103, 99, 102), ("2026-03-04", 109, 101, 108)])

    scritte = mature_plan_outcomes(db, commit=False)
    assert scritte == 1

    riga = db.query(PlanOutcome).one()
    assert riga.alert_id == a.id
    assert riga.esito == "tp1"
    assert riga.resolved_date == date(2026, 3, 4)
    assert riga.tp1_hit_date == date(2026, 3, 4)
    assert riga.stop_hit_date is None
    # La geometria e' congelata nella riga, non rinviata al calcolo.
    assert riga.entry == pytest.approx(100.0)
    assert riga.stop == pytest.approx(96.0)
    assert riga.r == pytest.approx(4.0)


def test_girare_due_volte_non_duplica(db: Session) -> None:
    """La maturazione gira a OGNI scansione: se non fosse idempotente il
    magazzino conterebbe lo stesso trade una volta al giorno, cioe'
    dichiarerebbe un campione che non esiste."""
    s = _titolo(db)
    _alert(db, s)
    _barre(db, s, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 109, 99, 108)])

    assert mature_plan_outcomes(db, commit=False) == 1
    assert mature_plan_outcomes(db, commit=False) == 0
    assert db.query(PlanOutcome).count() == 1


# ─── 2. L'ingresso e' DOPO lo scatto ───────────────────────────────────────

def test_la_gara_parte_dalla_barra_SUCCESSIVA_allo_scatto(db: Session) -> None:
    """⚠️ Il contratto piu' importante di questo servizio.

    La barra dello scatto contiene massimo e minimo dell'INTERA giornata,
    inclusa la parte PRECEDENTE all'alert. Contarla significherebbe attribuire
    al piano un movimento avvenuto prima che l'alert esistesse — un target
    «colpito» da un massimo segnato al mattino su un alert scattato nel
    pomeriggio. Il piano ne uscirebbe migliore di quanto e', in modo
    sistematico e invisibile.
    """
    s = _titolo(db)
    _alert(db, s, scattato="2026-03-02")
    _barre(db, s, [
        ("2026-03-02", 120, 90, 100),   # lo scatto: tocca TUTTO, non va contata
        ("2026-03-03", 103, 99, 102),
        ("2026-03-04", 109, 101, 108),
    ])

    mature_plan_outcomes(db, commit=False)
    riga = db.query(PlanOutcome).one()
    assert riga.resolved_date == date(2026, 3, 4), (
        "la barra dello scatto e' stata contata: il target risulta colpito il "
        "giorno stesso, da un massimo che precede l'alert"
    )
    assert riga.stop_hit_date is None, "anche il minimo dello scatto e' stato contato"


# ─── 3. Chi resta fuori, e perche' ─────────────────────────────────────────

def test_un_alert_senza_invalidazione_non_produce_nulla_e_non_esplode(db: Session) -> None:
    """I 2.508 alert storici dei sei detector scoperti sono in questo caso.

    Niente livello, niente piano, niente stop contro cui correre. Il ripiego
    corretto e' nessuna riga — non una riga con uno stop inventato, che
    sarebbe indistinguibile da una misurata.
    """
    s = _titolo(db)
    _alert(db, s, invalidazione=None)
    _barre(db, s, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 109, 99, 108)])

    assert mature_plan_outcomes(db, commit=False) == 0
    assert db.query(PlanOutcome).count() == 0


def test_un_trade_ancora_aperto_NON_viene_etichettato(db: Session) -> None:
    """Niente e' stato toccato e l'orizzonte non e' trascorso: la riga si
    scrivera' quando ci sara' qualcosa da scrivere."""
    s = _titolo(db)
    _alert(db, s)
    _barre(db, s, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 103, 99, 101), ("2026-03-04", 102, 98, 100)])

    assert mature_plan_outcomes(db, commit=False) == 0
    assert db.query(PlanOutcome).count() == 0


def test_un_alert_senza_barre_successive_non_produce_nulla(db: Session) -> None:
    s = _titolo(db)
    _alert(db, s)
    _barre(db, s, [("2026-03-01", 103, 99, 101)])   # tutte PRIMA dello scatto

    assert mature_plan_outcomes(db, commit=False) == 0


# ─── 4. L'orizzonte e' quello del detector ─────────────────────────────────

def test_l_orizzonte_e_quello_del_detector_non_un_numero_fisso(db: Session) -> None:
    """Lo stesso numero che usa il magazzino a orizzonte fisso, cosi' le due
    etichette coprono la stessa finestra e restano confrontabili."""
    from app.services.signal_drift_service import _horizon_days

    s = _titolo(db)
    _alert(db, s, detector="analyst_momentum")
    _barre(db, s, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 109, 99, 108)])

    mature_plan_outcomes(db, commit=False)
    riga = db.query(PlanOutcome).one()
    assert riga.horizon_days == _horizon_days("analyst_momentum")
    assert riga.horizon_days > 5, "un orizzonte lungo non deve leggersi come breve"


# ─── 5. Piu' titoli insieme ────────────────────────────────────────────────

def test_titoli_diversi_maturano_nella_stessa_passata(db: Session) -> None:
    s1, s2 = _titolo(db, "AAA"), _titolo(db, "BBB")
    _alert(db, s1)
    _alert(db, s2, tono="bear", invalidazione=104.0)
    _barre(db, s1, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 109, 99, 108)])
    _barre(db, s2, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 101, 91, 92)])

    assert mature_plan_outcomes(db, commit=False) == 2
    esiti = {r.stock_id: r.esito for r in db.query(PlanOutcome).all()}
    assert esiti[s1.id] == "tp1"
    assert esiti[s2.id] == "tp1"


def test_un_titolo_senza_barre_non_impedisce_agli_altri_di_maturare(db: Session) -> None:
    """⚠️ Un guasto per riga non deve costare la passata.

    E' la stessa forma per cui `ohlcv_service` cattura per titolo dentro il
    ciclo: un ticker morto non deve fermare gli altri novecentonovantanove.
    """
    s1, s2 = _titolo(db, "AAA"), _titolo(db, "BBB")
    _alert(db, s1)
    _alert(db, s2)
    _barre(db, s2, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 109, 99, 108)])   # solo il secondo ha barre

    assert mature_plan_outcomes(db, commit=False) == 1
    assert db.query(PlanOutcome).one().stock_id == s2.id


# ─── 6. Il ricalcolo storico: ricostruire SOLO dove e' esatto ──────────────
#
# I sei detector scoperti emettono il livello da adesso. I loro ~2.508 alert
# storici hanno `invalidation: None` nello snapshot per sempre, e resterebbero
# fuori dalla misura per settimane.
#
# Per QUATTRO di loro il livello si ricostruisce da un FATTO delle barre:
#   gap_and_go          la chiusura della barra precedente al gap
#   le tre divergenze   il minimo/massimo della barra del segnale, che e'
#                       l'ultimo pivot per costruzione (l'evento porta
#                       `date == pivot_dates[-1]`, verificato in events.py)
#
# Per gli altri DUE no: `adx_confirmation` vorrebbe ricalcolare un livello
# Donchian con un parametro che potrebbe essere cambiato, e `squeeze_expansion`
# la finestra di compressione. Un livello DEDOTTO applicato all'indietro e'
# esattamente cio' che questo repo ha imparato a non fare su SOXS: sembra
# perfettamente sano ed e' silenziosamente sbagliato.

def test_il_gap_storico_si_ricostruisce_dalla_chiusura_precedente(db: Session) -> None:
    s = _titolo(db)
    _alert(db, s, detector="gap_and_go", invalidazione=None, scattato="2026-03-02")
    _barre(db, s, [
        ("2026-02-27", 96, 94, 95.2),   # la chiusura PRIMA del gap: il livello
        ("2026-03-01", 101, 99, 100),   # la barra del segnale (gap)
        ("2026-03-03", 103, 99, 102),
        ("2026-03-04", 109, 101, 108),
    ])

    assert mature_plan_outcomes(db, commit=False, ricostruisci=True) == 1
    riga = db.query(PlanOutcome).one()
    assert riga.source == "ricostruito"
    assert riga.stop == pytest.approx(95.2)


def test_la_divergenza_storica_si_ricostruisce_dall_estremo_della_barra(db: Session) -> None:
    s = _titolo(db)
    _alert(db, s, detector="rsi_divergence", invalidazione=None, scattato="2026-03-02")
    _barre(db, s, [
        ("2026-03-01", 101, 88.5, 100),   # la barra del segnale: minimo = livello
        ("2026-03-03", 103, 99, 102),
        ("2026-03-04", 109, 101, 108),
    ])

    assert mature_plan_outcomes(db, commit=False, ricostruisci=True) == 1
    riga = db.query(PlanOutcome).one()
    assert riga.source == "ricostruito"
    assert riga.stop == pytest.approx(88.5)


def test_adx_e_squeeze_NON_si_ricostruiscono(db: Session) -> None:
    """⚠️ L'esclusione e' la parte importante, ed e' deliberata.

    Ricostruire un livello Donchian o una finestra di compressione vorrebbe
    dire ricalcolarli con parametri che potrebbero essere cambiati. Il
    risultato sarebbe indistinguibile da un livello misurato — che e'
    precisamente la ragione per cui non si fa.
    """
    s1, s2 = _titolo(db, "AAA"), _titolo(db, "BBB")
    _alert(db, s1, detector="adx_confirmation", invalidazione=None)
    _alert(db, s2, detector="squeeze_expansion", invalidazione=None)
    for s in (s1, s2):
        _barre(db, s, [("2026-03-01", 101, 88, 100), ("2026-03-03", 109, 99, 108)])

    assert mature_plan_outcomes(db, commit=False, ricostruisci=True) == 0
    assert db.query(PlanOutcome).count() == 0


def test_la_ricostruzione_e_SPENTA_per_la_scansione_normale(db: Session) -> None:
    """⚠️ Il percorso incrementale non deve mai ricostruire.

    Da adesso i sei detector emettono il livello, quindi un alert nuovo senza
    invalidazione e' un alert che non ne ha una — e riempirlo all'indietro
    renderebbe `source='emesso'` una promessa falsa. Il ricalcolo storico e'
    un'operazione dichiarata e una tantum.
    """
    s = _titolo(db)
    _alert(db, s, detector="gap_and_go", invalidazione=None)
    _barre(db, s, [("2026-02-27", 96, 94, 95.2), ("2026-03-03", 109, 99, 108)])

    assert mature_plan_outcomes(db, commit=False) == 0


def test_un_livello_EMESSO_non_viene_mai_sovrascritto_da_una_ricostruzione(db: Session) -> None:
    s = _titolo(db)
    _alert(db, s, detector="gap_and_go", invalidazione=96.0)
    _barre(db, s, [("2026-02-27", 96, 94, 80.0),    # il livello che la ricostruzione userebbe
                   ("2026-03-02", 101, 99, 100.0),  # la barra d'ingresso
                   ("2026-03-03", 109, 99, 108)])

    assert mature_plan_outcomes(db, commit=False, ricostruisci=True) == 1
    riga = db.query(PlanOutcome).one()
    assert riga.source == "emesso"
    assert riga.stop == pytest.approx(96.0), "la ricostruzione ha scavalcato il livello vero"


# ─── 7. Lo script di ricalcolo ─────────────────────────────────────────────

def test_lo_script_in_sola_lettura_NON_scrive(db: Session, monkeypatch) -> None:
    """⚠️ Una modalita' «sola lettura» che lascia le righe in sessione e' peggio
    di nessuna modalita' sola lettura: il primo commit di qualcun altro le
    scriverebbe comunque, e chi ha letto il rapporto crederebbe di non aver
    toccato niente.

    Il monkeypatch di SessionLocal non e' una formalita': lo script lo importa
    al caricamento del modulo, quindi senza scriverebbe nel database di
    SVILUPPO — la trappola gia' documentata in test_institutionals_catchup.
    """
    from app.core import db as db_module
    from app.scripts import backfill_plan_outcomes

    s = _titolo(db)
    _alert(db, s)
    _barre(db, s, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 109, 99, 108)])
    db.commit()

    monkeypatch.setattr(backfill_plan_outcomes, "SessionLocal", db_module.SessionLocal)
    backfill_plan_outcomes.run(applica=False)

    assert db.query(PlanOutcome).count() == 0, "la sola lettura ha scritto"


def test_lo_script_con_applica_scrive(db: Session, monkeypatch) -> None:
    from app.core import db as db_module
    from app.scripts import backfill_plan_outcomes

    s = _titolo(db)
    _alert(db, s)
    _barre(db, s, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 109, 99, 108)])
    db.commit()

    monkeypatch.setattr(backfill_plan_outcomes, "SessionLocal", db_module.SessionLocal)
    backfill_plan_outcomes.run(applica=True)

    assert db.query(PlanOutcome).count() == 1


def test_main_inoltra_i_flag_alla_run(monkeypatch) -> None:
    """⚠️ Il passaggio dei flag e' esattamente cio' che si rompe in silenzio.

    Un `--applica` non inoltrato produce uno script che gira, stampa un
    rapporto, esce con zero e non scrive MAI — e il modo in cui ce se ne
    accorge e' che dopo settimane il magazzino e' ancora vuoto.
    """
    import sys

    from app.scripts import backfill_plan_outcomes

    visti: list[tuple[bool, bool]] = []
    monkeypatch.setattr(backfill_plan_outcomes, "run",
                        lambda applica=False, ricostruisci=False:
                            visti.append((applica, ricostruisci)))

    monkeypatch.setattr(sys, "argv", ["backfill_plan_outcomes"])
    backfill_plan_outcomes.main()
    monkeypatch.setattr(sys, "argv", ["backfill_plan_outcomes", "--applica", "--ricostruisci"])
    backfill_plan_outcomes.main()

    assert visti == [(False, False), (True, True)]


# ─── 8. L'ancora e' la PRIMA emissione, non l'ultima revisione ─────────────
#
# ⚠️ Difetto trovato il 2026-09-18, misurato in produzione. Un alert e' una
# riga VIVA: finche' il segnale persiste, ogni scansione lo rivede e riscrive
# sia `triggered_at` sia `trigger_price` (signal_scan_service ~287-290). Su
# 8.736 alert, 7.010 (80%) hanno almeno una revisione e 6.345 (73%) hanno un
# `first_emitted_at` ANTERIORE a `triggered_at` — uno ne ha 103.
#
# Ancorare la gara a quei due campi rende la misura DIPENDENTE DAL MOMENTO in
# cui gira la maturazione: la stessa riga, maturata due giorni prima, avrebbe
# un altro ingresso e un altro esito. Un magazzino il cui contenuto dipende da
# quando lo si e' guardato non e' una misura.
#
# `first_emitted_at` non cambia mai: e' il primo istante in cui quell'alert e'
# esistito, cioe' il primo in cui si sarebbe potuto agire.

def _alert_rivisto(db: Session, stock: Stock, *, prima_emissione: str,
                   rivisto_il: str, prezzo_rivisto: float) -> Alert:
    """Un alert come sono l'80% di quelli veri: emesso una volta, riscritto poi."""
    import json as _json
    a = _alert(db, stock, scattato=rivisto_il, prezzo=prezzo_rivisto)
    snap = _json.loads(a.snapshot)
    snap["first_emitted_at"] = f"{prima_emissione}T23:32:00+00:00"
    snap["amend_count"] = 13
    a.snapshot = _json.dumps(snap)
    a.signal_date = date.fromisoformat(prima_emissione)
    db.flush()
    return a


def test_l_ingresso_e_il_prezzo_della_PRIMA_emissione_non_dell_ultima_revisione(
    db: Session,
) -> None:
    s = _titolo(db)
    _alert_rivisto(db, s, prima_emissione="2026-03-02", rivisto_il="2026-03-06",
                   prezzo_rivisto=140.0)
    _barre(db, s, [
        ("2026-03-02", 101, 99, 100.0),   # la chiusura alla prima emissione
        ("2026-03-03", 103, 99, 102),
        ("2026-03-04", 109, 101, 108),
        ("2026-03-05", 112, 107, 110),
        ("2026-03-06", 145, 138, 140.0),  # la chiusura all'ultima revisione
    ])

    assert mature_plan_outcomes(db, commit=False) == 1
    riga = db.query(PlanOutcome).one()
    assert riga.entry == pytest.approx(100.0), (
        "l'ingresso e' il prezzo riscritto all'ultima revisione, non quello della "
        "prima emissione"
    )
    assert riga.entry_date == date(2026, 3, 2)
    # E la gara parte dal 3, quindi il target del 4 e' colpito.
    assert riga.resolved_date == date(2026, 3, 4)


def test_la_misura_NON_dipende_da_quando_gira_la_maturazione(db: Session) -> None:
    """⚠️ La proprieta', non il valore. E' il test che rende il difetto chiuso.

    Due alert identici salvo il momento dell'ultima revisione — cioe' la stessa
    situazione vista da due maturazioni che girano in giorni diversi — devono
    produrre lo STESSO esito. Con l'ancora sbagliata divergono, ed e'
    esattamente cio' che rendeva il magazzino non riproducibile.
    """
    s1, s2 = _titolo(db, "AAA"), _titolo(db, "BBB")
    barre = [
        ("2026-03-02", 101, 99, 100.0),
        ("2026-03-03", 103, 99, 102),
        ("2026-03-04", 109, 101, 108),
        ("2026-03-05", 112, 107, 110),
        ("2026-03-06", 145, 138, 140.0),
    ]
    # Stessa prima emissione, revisioni in due momenti diversi.
    _alert_rivisto(db, s1, prima_emissione="2026-03-02", rivisto_il="2026-03-04",
                   prezzo_rivisto=108.0)
    _alert_rivisto(db, s2, prima_emissione="2026-03-02", rivisto_il="2026-03-06",
                   prezzo_rivisto=140.0)
    _barre(db, s1, barre)
    _barre(db, s2, barre)

    mature_plan_outcomes(db, commit=False)
    righe = {r.stock_id: r for r in db.query(PlanOutcome).all()}
    a, b = righe[s1.id], righe[s2.id]
    assert a.entry == b.entry
    assert a.entry_date == b.entry_date
    assert a.esito == b.esito
    assert a.resolved_date == b.resolved_date
    assert a.r_multiple == pytest.approx(b.r_multiple)


def test_senza_first_emitted_at_si_ripiega_su_triggered_at(db: Session) -> None:
    """I 116 alert storici (l'1,3%) che precedono il campo. Il ripiego e'
    dichiarato: e' il meglio disponibile, non una ricostruzione."""
    s = _titolo(db)
    _alert(db, s, scattato="2026-03-02")   # `_alert` non mette first_emitted_at
    _barre(db, s, [("2026-03-02", 101, 99, 100.0), ("2026-03-03", 109, 99, 108)])

    assert mature_plan_outcomes(db, commit=False) == 1
    assert db.query(PlanOutcome).one().entry_date == date(2026, 3, 2)


def test_senza_una_barra_alla_prima_emissione_non_si_misura(db: Session) -> None:
    """Niente prezzo d'ingresso, niente geometria. Il ripiego corretto e'
    nessuna riga, non il primo prezzo che capita."""
    s = _titolo(db)
    _alert_rivisto(db, s, prima_emissione="2026-03-02", rivisto_il="2026-03-06",
                   prezzo_rivisto=140.0)
    _barre(db, s, [("2026-03-05", 112, 107, 110), ("2026-03-06", 145, 138, 140)])

    assert mature_plan_outcomes(db, commit=False) == 0
