"""Il seme copre `/institutionals`, e non dipende da QUANDO gira (FA-068).

Prima di questa semina `seed_e2e` non scriveva una riga in
`institutional_holdings`: in CI la pagina rendeva tre tabelle vuote e il gate
misurava cio' che capitava. `scrollable-region-focusable` e' passato da 0 a 2
fra due corse a sei minuti di distanza, su una rotta che nessun commit aveva
toccato.

Due famiglie di asserzioni, e servono entrambe:

- **Pavimenti.** Le tre regioni scorrevoli sono il difetto che il gate aveva
  trovato, e una regione che non ha righe abbastanza non scorre: il controllo
  di accessibilita' su di essa sarebbe vero di niente. Qui si pretende il
  numero di righe che le fa scorrere.
- **Ripetibilita'.** Il seme ha gia' pagato tre volte una dipendenza
  dall'orologio (barre, ancora oraria, data dei segnali). Le date dei filing
  sono la quarta occasione, e la pagina ha una soglia — la pastiglia «stale»
  oltre i 183 giorni — che le trasformerebbe in un numero di elementi resi.
"""

from collections import Counter
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.institutional import InstitutionalFiling, InstitutionalHolding
from app.scripts.seed_e2e import (
    FONDI,
    RITARDO_DEPOSITO,
    _fine_trimestre,
    _trimestre,
    semina_istituzionali,
)
from app.services.institutional_service import (
    MAX_FILING_AGE_MONTHS,
    filings_refresh_is_stale,
    get_aggregate_stats,
    list_institutionals,
)

#: La soglia della pastiglia in `InstitutionalsPage.isStale`.
SOGLIA_STALE_GIORNI = 183
#: Il taglio del cruscotto in `_freshness_cutoff`, con la stessa aritmetica.
TAGLIO_CRUSCOTTO_GIORNI = int(30.4 * MAX_FILING_AGE_MONTHS)

#: Un anno e un giorno di «oggi», bisestile compreso: ogni posizione possibile
#: dentro un trimestre, piu' il salto d'anno.
ANNO = [date(2027, 12, 31) - timedelta(days=k) for k in range(367)]

#: I parametri con cui la pagina chiama il cruscotto (`useInstitutionalsAggregate`).
PARAMETRI_PAGINA = {"most_picked_limit": 25, "recent_actions_limit": 15}

#: Le schede acquisti/vendite rendono `slice(0, 12)`, e dodici righe con
#: ticker e nome impilati superano i 30rem della regione. Sotto questo numero
#: la regione non scorre e `scrollable-region-focusable` non e' esercitato.
RIGHE_PER_SCORRERE = 12


def _sessione() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


# ─── Il calendario dei trimestri ──────────────────────────────────────────


def test_fine_trimestre_sui_bordi():
    assert _fine_trimestre(date(2026, 9, 30)) == date(2026, 9, 30)
    assert _fine_trimestre(date(2026, 9, 29)) == date(2026, 6, 30)
    assert _fine_trimestre(date(2026, 1, 1)) == date(2025, 12, 31)
    assert _fine_trimestre(date(2024, 3, 31)) == date(2024, 3, 31)


@pytest.mark.parametrize("oggi", ANNO[::7] + ANNO[-3:], ids=str)
def test_nessun_filing_esiste_prima_di_poter_essere_depositato(oggi):
    """Un periodo finito ieri non puo' avere un 13F: si deposita fino a 45
    giorni dopo. Un filing datato nel futuro renderebbe una «Q-end» che non e'
    ancora successa."""
    for indietro in range(4):
        periodo = _trimestre(oggi, indietro)
        assert periodo + timedelta(days=RITARDO_DEPOSITO) <= oggi


def test_ogni_fondo_legge_lo_stesso_stato_OGNI_giorno_dell_anno():
    """⚠️ Il test che tiene chiusa la quarta dipendenza dall'orologio.

    Per ciascun «oggi» di un anno intero: i fondi freschi restano sotto i 183
    giorni della pastiglia, il fondo vecchio sta sopra, e nessuno esce dai 18
    mesi del cruscotto. Se una sola data dell'anno rompesse una delle tre, il
    numero di pastiglie a schermo — o di righe nelle schede — dipenderebbe dal
    giorno in cui gira la CI.
    """
    for oggi in ANNO:
        for slug, *_, indietro in FONDI:
            eta = (oggi - _trimestre(oggi, indietro)).days
            eta_precedente = (oggi - _trimestre(oggi, indietro + 1)).days
            assert eta_precedente < TAGLIO_CRUSCOTTO_GIORNI, (oggi, slug)
            if indietro == 0:
                assert eta <= SOGLIA_STALE_GIORNI, (oggi, slug, eta)
            else:
                assert eta > SOGLIA_STALE_GIORNI, (oggi, slug, eta)


def test_il_controllo_negativo_UN_trimestre_indietro_attraversa_la_soglia():
    """⚠️ Senza questo, il test sopra sembra una formalita'.

    Il fondo vecchio sta DUE trimestri indietro, non uno, e la ragione e' qui:
    un trimestre vale 90-92 giorni, quindi il filing di un trimestre fa ha
    un'eta' fra 135 e 228 giorni e sta a cavallo dei 183 — «stale» in certi
    giorni e fresco in altri. La prima stesura del seme aveva esattamente
    questa aritmetica sbagliata nel docstring, scritta prima di misurare.
    """
    stati = {(oggi - _trimestre(oggi, 1)).days > SOGLIA_STALE_GIORNI for oggi in ANNO}
    assert stati == {True, False}, "un trimestre indietro sembra stabile: il controllo non prova niente"


def test_esattamente_un_fondo_e_vecchio():
    """Il ramo «stale» deve essere esercitato, ma da UNA riga: se lo fossero
    tutte, la pastiglia smetterebbe di distinguere qualcosa."""
    assert sum(1 for *_, indietro in FONDI if indietro > 0) == 1


# ─── Cio' che la pagina rende ─────────────────────────────────────────────


def test_le_tre_regioni_hanno_righe_abbastanza_da_scorrere(db: Session):
    """⚠️ Il pavimento. Le tre regioni `max-h-[30rem]` sono il difetto che il
    gate aveva trovato, e una regione con quattro righe non scorre: il suo
    controllo di accessibilita' passerebbe su niente."""
    semina_istituzionali(db, date.today())
    agg = get_aggregate_stats(db, **PARAMETRI_PAGINA)

    assert len(agg.most_picked) > RIGHE_PER_SCORRERE
    assert len(agg.recent_buys) >= RIGHE_PER_SCORRERE
    assert len(agg.recent_sells) >= RIGHE_PER_SCORRERE


def test_tutte_e_quattro_le_azioni_arrivano_dal_codice_vero(db: Session):
    """Le etichette le calcola `compute_qoq_deltas`, non il seme. Se il seme
    smettesse di passare dal codice vero — o lo chiamasse sul filing sbagliato
    — il primo sintomo sarebbe un'azione che manca."""
    semina_istituzionali(db, date.today())
    agg = get_aggregate_stats(db, **PARAMETRI_PAGINA)

    assert {r.action for r in agg.recent_buys} == {"new", "add"}
    assert {r.action for r in agg.recent_sells} == {"reduce", "sold_out"}


def test_le_due_classi_alphabet_contano_come_un_titolo_solo(db: Session):
    """GOOG e GOOGL sono seminate apposta: il cruscotto le fonde, e un fondo
    che le tiene entrambe deve contare una volta."""
    semina_istituzionali(db, date.today())
    agg = get_aggregate_stats(db, **PARAMETRI_PAGINA)
    tickers = [r.ticker for r in agg.most_picked]

    assert "GOOG" in tickers
    assert "GOOGL" not in tickers
    goog = next(r for r in agg.most_picked if r.ticker == "GOOG")
    assert goog.holder_count <= len(FONDI)


def test_la_lista_ha_tutti_i_fondi_e_uno_solo_vecchio(db: Session):
    semina_istituzionali(db, date.today())
    fondi = list_institutionals(db)

    assert len(fondi) == len(FONDI)
    vecchi = [f for f in fondi if (date.today() - f.latest_period_end).days > SOGLIA_STALE_GIORNI]
    assert len(vecchi) == 1


def test_rieseguire_il_seme_non_duplica(db: Session):
    semina_istituzionali(db, date.today())
    prima = db.scalar(select(func.count()).select_from(InstitutionalHolding))
    semina_istituzionali(db, date.today())
    dopo = db.scalar(select(func.count()).select_from(InstitutionalHolding))

    assert prima == dopo
    assert db.scalar(select(func.count()).select_from(InstitutionalFiling)) == 2 * len(FONDI)


def _fotografia(oggi: date) -> tuple[Counter, int, int, int]:
    s = _sessione()
    try:
        semina_istituzionali(s, oggi)
        agg = get_aggregate_stats(s, **PARAMETRI_PAGINA)
        azioni = Counter(
            (r.ticker, r.institutional_slug, r.action)
            for r in agg.recent_buys + agg.recent_sells
        )
        return azioni, len(agg.most_picked), len(agg.recent_buys), len(agg.recent_sells)
    finally:
        s.close()


@pytest.mark.parametrize("scarto", [1, 6, 100])
def test_il_contenuto_non_dipende_dal_giorno(scarto):
    """Stessi fondi, stesse posizioni, stesse azioni, qualunque sia «oggi».

    Lo scarto di 100 giorni cambia TRIMESTRE, cioe' le date di tutti i filing:
    e' il caso che separa un seme deterministico da uno che lo sembra.
    """
    assert _fotografia(date.today()) == _fotografia(date.today() - timedelta(days=scarto))


def test_dopo_la_semina_l_avvio_NON_lancia_gli_scraper_veri(db: Session):
    """⚠️ Il meccanismo del «0 -> 2 fra due corse a sei minuti», fissato come
    contratto invece che lasciato come effetto collaterale.

    `_catch_up_institutionals_on_boot` lancia Dataroma e SEC 13F veri quando
    `filings_refresh_is_stale` risponde vero — e risponde vero anche quando
    NON ESISTE nessun filing. Il database del gate nasceva vuoto, quindi ogni
    corsa CI avviava gli scraper reali in un thread mentre Playwright misurava:
    `/institutionals` a volte veniva visitata prima che finissero, a volte dopo.

    La semina li spegne perche' i filing appena scritti sono freschi. Se un
    giorno il seme li retrodatasse — per esempio per imitare un `created_at`
    realistico — questo diventa rosso invece di riaprire il difetto in
    silenzio.
    """
    # Il controllo negativo nello stesso test: a database vuoto gli scraper
    # partirebbero, cioe' la condizione che la semina deve spegnere e' reale.
    assert filings_refresh_is_stale(db) is True

    semina_istituzionali(db, date.today())
    db.flush()

    assert filings_refresh_is_stale(db) is False
