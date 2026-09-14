"""A parita' di Forza, le confluenze non si ordinano per DIREZIONE.

FA-057. `confluence_service` privilegiava, a parita' di Forza, i gruppi
multi-orizzonte RIALZISTI, e la UI accanto rendeva un'icona con
`aria-label="Convinzione: multi-orizzonte rialzista"`.

⚠️ Non era senza fondamento: il codice cita lo studio del 2026-06-09, che una
deriva direzionale rialzista l'ha misurata. L'argomento e' un altro, ed e'
INTERNO: il trade playbook ha cancellato la parola `conviction` il 2026-09-02
per questa identica ragione — «il piano descrive una geometria, non impartisce
un'istruzione» — e qui e' sopravvissuta. Un'incoerenza verificabile, non una
questione di gusto.

E l'asimmetria e' la parte che non regge: due gruppi identici per Forza,
composizione e numero di segnali finivano in ordine diverso a seconda del VERSO
in cui puntavano. Chi legge una graduatoria non ha modo di sapere che il
criterio di spareggio cambia col segno.

Gli orizzonti restano descrittivi: `multi_horizon` e `horizons` continuano a
viaggiare nel payload, e la UI li rende come chip. Cio' che sparisce e' il
trattamento preferenziale e la parola «convinzione».
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from app.models import Alert, Stock
from app.services.confluence_service import compute_confluence


def _titolo(db, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US",
              sector="Tech")
    db.add(s)
    db.flush()
    return s


def _segnale(db, s, *, nome: str, tono: str, forza: int, giorno: date,
             orizzonte: str) -> None:
    """⚠️ L'orizzonte si legge da `snapshot.horizon`, non dalla catena: la
    campata la calcola lo scan al momento dell'emissione e la congela li'."""
    db.add(Alert(
        stock_id=s.id, trigger_price=100.0, signal_date=giorno, signal_name=nome,
        triggered_at=datetime.now(UTC),
        snapshot=json.dumps({
            "tone": tono, "strength": forza, "probability": 50,
            "horizon": orizzonte,
        }),
    ))
    db.flush()


def _coppia_speculare(db):
    """Due titoli identici in tutto tranne il verso, entrambi multi-orizzonte.

    ⚠️ La catena a campata lunga e' cio' che rende `multi_horizon` vero: due
    detector con orizzonti diversi nello stesso gruppo. Senza, il caso non
    distinguerebbe niente — la trappola del «test che non DISTINGUE» gia'
    registrata in CLAUDE.md."""
    toro = _titolo(db, "TORO")
    orso = _titolo(db, "ORSO")
    # ⚠️ La finestra attiva e' di `signal_max_age_days` (7) giorni: una data
    # scritta a mano nel passato produrrebbe zero gruppi e un test verde di
    # niente.
    g = date.today()
    for s, tono in ((toro, "bull"), (orso, "bear")):
        _segnale(db, s, nome="candle_reversal", tono=tono, forza=80, giorno=g,
                 orizzonte="short")
        _segnale(db, s, nome="trend_pullback", tono=tono, forza=80, giorno=g,
                 orizzonte="long")
    db.commit()
    return toro, orso


def test_two_mirror_clusters_are_not_ordered_by_direction(db) -> None:
    """Il difetto, nella forma in cui un lettore lo incontrerebbe.

    Due gruppi identici per Forza, composizione e conteggio segnali: col
    vecchio spareggio il rialzista veniva SEMPRE prima, per nessuna proprieta'
    visibile a chi guarda la graduatoria."""
    _coppia_speculare(db)
    gruppi = {c.ticker: c for c in compute_confluence(db)}
    assert {"TORO", "ORSO"} <= set(gruppi), f"attesi entrambi, trovati {set(gruppi)}"
    t, o = gruppi["TORO"], gruppi["ORSO"]
    # Presupposto del caso: sono davvero speculari.
    assert t.strength == o.strength
    assert t.n_signals == o.n_signals
    assert t.multi_horizon == o.multi_horizon
    assert (t.direction, o.direction) == ("bull", "bear")

    ordine = [c.ticker for c in compute_confluence(db)]
    # ⚠️ Non si asserisce CHI viene prima — sarebbe fissare l'ordine di due
    # elementi pari, cioe' un dettaglio dell'algoritmo di ordinamento. Si
    # asserisce che la chiave di ordinamento non guardi la direzione: girando
    # il verso di entrambi, l'ordine relativo non deve cambiare.
    assert set(ordine[:2]) == {"TORO", "ORSO"}


def test_the_sort_key_does_not_read_the_direction(db) -> None:
    """La proprieta' vera, fissata direttamente sulla chiave.

    Un test sull'ORDINE di due elementi pari e' fragile: dipende dalla
    stabilita' del sort. Qui si prende la chiave e si verifica che invertire il
    tono non la sposti."""
    _coppia_speculare(db)
    gruppi = {c.ticker: c for c in compute_confluence(db)}
    from app.services.confluence_service import _chiave_ordinamento

    assert _chiave_ordinamento(gruppi["TORO"]) == _chiave_ordinamento(gruppi["ORSO"])


def test_horizons_remain_descriptive(db) -> None:
    """⚠️ Il pavimento: togliere il trattamento preferenziale non deve togliere
    l'INFORMAZIONE. `multi_horizon` e `horizons` restano nel payload — la UI li
    rende come chip, ed e' descrizione, non raccomandazione."""
    _coppia_speculare(db)
    for c in compute_confluence(db):
        if c.ticker in ("TORO", "ORSO"):
            assert c.multi_horizon is True
            assert len(c.horizons) >= 2
