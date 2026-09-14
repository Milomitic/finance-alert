"""Un setup che si riforma e' un EPISODIO NUOVO, non la stessa riga riusata.

FA-061. `upsert_setup` riattivava la riga esistente azzerando `resolved_at`,
`converted_alert_id` e `lead_days`, e il vincolo `UniqueConstraint(stock_id,
detector)` rendeva impossibile conservarne piu' di uno. Misurato in produzione:
**2.050 setup su 2.050 coppie (stock, detector)** — i due numeri coincidono per
costruzione, quindi ogni episodio precedente e' stato sovrascritto e non e'
contato da nessuna parte.

⚠️ Quanti siano NON e' misurabile a posteriori, ed e' la ragione per cui la
voce dichiara la perdita invece di stimarla: la riattivazione non lascia
traccia di se'.

⚠️ E una decisione che va detta, perche' riguarda un numero a schermo. Il tetto
di convenienza CANCELLAVA la riga (`db.delete`), quindi un setup decaduto
spariva; ora viene CHIUSO con la sua ragione, il che conserva la storia ma
gonfierebbe il denominatore del tasso di conversione — 9/18 = 50,0% oggi. Le
chiusure per decadimento sono quindi ESCLUSE dal denominatore, con la ragione
scritta: il numero a schermo resta identico, le righe esistono, e la domanda
«un setup decaduto e' una mancata conversione?» diventa rispondibile invece di
essere decisa di nascosto da un DELETE.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import ScanRun, Stock, StockSetup
from app.models.stock_setup import (
    REASON_AGED,
    REASON_DECAYED,
    REASON_STALE,
    STATUS_ACTIVE,
    STATUS_CONVERTED,
    STATUS_EXPIRED,
)
from app.services import setup_service
from app.services.setup_service import _MIN_SCANS_BEFORE_EXPIRY as _MIN_SCANS
from app.signals.setups.base import SetupMatch


def _titolo(db, ticker: str = "EPIS") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    return s


def _match(tone: str = "bull") -> SetupMatch:
    return SetupMatch(detector="candle_reversal", tone=tone, proximity=0.8,
                      missing="manca la chiusura", distance_atr=0.5)


@pytest.fixture
def punteggio(monkeypatch):
    """Il punteggio e' controllato dal test: qui si verifica il CICLO DI VITA,
    non la taratura della convenienza."""
    def imposta(v: float) -> None:
        monkeypatch.setattr(setup_service, "convenience", lambda *a, **k: v)
    imposta(80.0)
    return imposta


# ─── 1. Gli episodi si conservano ────────────────────────────────────────


def test_a_reformed_setup_opens_a_NEW_episode(db, punteggio) -> None:
    """Il cuore di FA-061.

    ⚠️ Col comportamento vecchio la riga veniva riusata e i tre campi
    dell'episodio precedente azzerati, quindi «il setup convertito a giugno»
    smetteva di esistere nel momento in cui la condizione si riformava."""
    s = _titolo(db)
    primo = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    id_primo = primo.id
    # Si chiude convertendo.
    primo.status = STATUS_CONVERTED
    primo.resolved_at = datetime.now(UTC)
    primo.converted_alert_id = None
    primo.lead_days = 4
    db.flush()

    # La condizione si riforma.
    secondo = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()

    assert secondo.id != id_primo, "la riga e' stata riusata invece di aprirne una nuova"
    righe = db.query(StockSetup).filter(StockSetup.stock_id == s.id).all()
    assert len(righe) == 2
    vecchio = next(r for r in righe if r.id == id_primo)
    # ⚠️ L'episodio chiuso conserva TUTTO: e' il numero che la funzione esiste
    # per riportare.
    assert vecchio.status == STATUS_CONVERTED
    assert vecchio.resolved_at is not None
    assert vecchio.lead_days == 4
    assert secondo.status == STATUS_ACTIVE
    assert secondo.lead_days is None


def test_an_open_episode_is_still_UPDATED_not_duplicated(db, punteggio) -> None:
    """L'altra meta' del confine, e il pavimento del test sopra: finche'
    l'episodio e' APERTO la ri-rilevazione lo aggiorna, perche' `first_seen_at`
    deve continuare a puntare all'inizio dell'attesa — e' cio' da cui
    `lead_days` si misura."""
    s = _titolo(db)
    primo = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    inizio = primo.first_seen_at
    secondo = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()

    assert secondo.id == primo.id
    assert secondo.first_seen_at == inizio
    assert db.query(StockSetup).filter(StockSetup.stock_id == s.id).count() == 1


def test_only_ONE_episode_can_be_open_at_a_time(db, punteggio) -> None:
    """L'invariante che sostituisce il vincolo vecchio. ⚠️ Non «una riga per
    coppia» — quella impediva la storia — ma «un episodio APERTO per coppia»,
    che e' la cosa che serviva davvero."""
    s = _titolo(db)
    setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    db.add(StockSetup(
        stock_id=s.id, detector="candle_reversal", tone="bull", proximity=0.8,
        convenience=70.0, missing="x", status=STATUS_ACTIVE,
        first_seen_at=datetime.now(UTC), last_seen_at=datetime.now(UTC),
    ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_two_CLOSED_episodes_coexist(db, punteggio) -> None:
    """Cio' che il vincolo vecchio rendeva impossibile, ed e' tutto il punto:
    due attese concluse sulla stessa coppia sono due fatti, non un duplicato."""
    s = _titolo(db)
    for _ in range(2):
        r = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
        db.flush()
        r.status = STATUS_EXPIRED
        r.resolved_at = datetime.now(UTC)
        r.closed_reason = REASON_STALE
        db.flush()
    assert db.query(StockSetup).filter(StockSetup.stock_id == s.id).count() == 2


# ─── 2. Le ragioni di chiusura, che il codice calcolava e buttava via ────


def test_a_setup_below_the_bar_is_CLOSED_not_deleted(db, punteggio) -> None:
    """⚠️ Prima era `db.delete(row)`: l'episodio spariva, e con lui la prova che
    quella condizione si fosse mai formata. La lista attiva si accorcia lo
    stesso, perche' filtra su `status == active`; cio' che cambia e' che il
    fatto resta scritto."""
    s = _titolo(db)
    punteggio(80.0)
    r = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    id_r = r.id

    punteggio(10.0)   # sotto `setup_min_convenience`
    assert setup_service.upsert_setup(db, stock_id=s.id, match=_match()) is None
    db.flush()

    riga = db.get(StockSetup, id_r)
    assert riga is not None, "la riga e' stata cancellata invece che chiusa"
    assert riga.status == STATUS_EXPIRED
    assert riga.closed_reason == REASON_DECAYED
    assert riga.resolved_at is not None


def test_expiry_records_WHICH_of_the_two_reasons(db, punteggio) -> None:
    """⚠️ `expire_stale_setups` distingueva gia' «decaduto» da «scaduto per
    eta'» — li contava separatamente nel log, col commento che spiega perche'
    sono diversi — e poi scriveva entrambi come `expired` senza dire quale. La
    distinzione era calcolata e buttata via."""
    s = _titolo(db)
    ora = datetime.now(UTC)
    # Decaduto: non piu' visto da tempo, ma nato ieri.
    decaduto = StockSetup(
        stock_id=s.id, detector="sr_flip", tone="bull", proximity=0.8,
        convenience=70.0, missing="x", status=STATUS_ACTIVE,
        first_seen_at=ora - timedelta(days=1), last_seen_at=ora - timedelta(days=30),
    )
    # Invecchiato: visto ieri, ma aperto da due mesi.
    invecchiato = StockSetup(
        stock_id=s.id, detector="volume_breakout", tone="bull", proximity=0.8,
        convenience=70.0, missing="x", status=STATUS_ACTIVE,
        first_seen_at=ora - timedelta(days=60), last_seen_at=ora - timedelta(hours=1),
    )
    db.add_all([decaduto, invecchiato])
    # ⚠️ La precondizione che il mio primo tentativo aveva mancato, ed e'
    # scritta nel docstring della funzione: la scadenza e' GUARDATA sulle
    # scansioni effettivamente girate, perche' una fase senza scansioni
    # riuscite — l'app giu', un job che va in crash — sembra identica a «le
    # condizioni sono decadute». Senza queste righe la funzione salta tutto e
    # ha ragione a farlo.
    for i in range(_MIN_SCANS):
        db.add(ScanRun(kind="universe", trigger="cron", status="success",
                       started_at=ora - timedelta(hours=i + 2),
                       completed_at=ora - timedelta(hours=i + 1)))
    db.commit()

    setup_service.expire_stale_setups(db)
    db.commit()

    assert decaduto.status == STATUS_EXPIRED
    assert decaduto.closed_reason == REASON_STALE
    assert invecchiato.status == STATUS_EXPIRED
    assert invecchiato.closed_reason == REASON_AGED


# ─── 3. Il denominatore del tasso non cambia ─────────────────────────────


def test_a_decayed_setup_is_NOT_a_failed_conversion(db, punteggio) -> None:
    """⚠️ La decisione che tiene fermo un numero a schermo.

    Conservare le chiusure per decadimento gonfierebbe il denominatore del
    tasso di conversione, che oggi legge 9/18 = 50,0% in produzione. Un setup
    ritirato perche' ha smesso di meritare attenzione non ha MAI avuto la
    possibilita' di convertire: contarlo come fallimento misurerebbe il
    ricambio della shortlist, non il valore del setup.

    Restano nel denominatore le due scadenze vere — `stale` e `aged` — perche'
    quelle l'occasione ce l'hanno avuta e non l'hanno colta."""
    s = _titolo(db)
    ora = datetime.now(UTC)
    comuni = dict(stock_id=s.id, tone="bull", proximity=0.8, convenience=70.0,
                  missing="x", shortlisted=True, first_seen_at=ora, last_seen_at=ora)
    db.add_all([
        StockSetup(detector="a", status=STATUS_CONVERTED, resolved_at=ora, **comuni),
        StockSetup(detector="b", status=STATUS_EXPIRED, resolved_at=ora,
                   closed_reason=REASON_STALE, **comuni),
        StockSetup(detector="c", status=STATUS_EXPIRED, resolved_at=ora,
                   closed_reason=REASON_DECAYED, **comuni),
    ])
    db.commit()

    st = setup_service.conversion_stats(db)
    # 1 convertito, 1 scaduto VERO, il decaduto fuori: 1/2 = 50%.
    assert st["converted"] == 1
    assert st["expired"] == 1, "il decaduto e' finito nel denominatore"
    assert st["conversion_rate"] == pytest.approx(0.5)
    # ⚠️ Ma il decaduto non e' invisibile: esiste e si conta a parte, altrimenti
    # escluderlo sarebbe indistinguibile dal cancellarlo.
    assert st["decayed"] == 1
