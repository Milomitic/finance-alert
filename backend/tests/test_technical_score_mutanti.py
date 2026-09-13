"""I confini della lente Tecnico, che nessun test percorreva.

⚠️ La sonda di mutazione ne uccideva 15 su 107 — il punteggio peggiore del
progetto. Non e' trascuratezza: i test esistenti sono ORDINALI («un titolo in
salita batte uno in discesa», «il composito non si muove quando arriva un
segnale»), che e' il modo giusto di verificare un punteggio. Fissare i valori
esatti renderebbe rossa ogni ritaratura legittima.

Ma un'asserzione ordinale sopravvive a quasi qualunque modifica di una
costante: se il peso del trend passasse da 0,28 a 1,28, un titolo in salita
continuerebbe a battere uno in discesa. Il 15% e' la firma di quella scelta,
non un difetto.

Quindi qui si fissa CIO' CHE E' UN CONTRATTO e si lascia libero cio' che e'
una taratura:

- contratto: le tre bande di postura sono ordinate, esaustive e col bordo
  INCLUSO; sotto una soglia di barre non si calcola niente; una serie piatta
  non divide per zero; il ricalcolo di un titolo tocca QUEL titolo.
- taratura: le finestre (50/200/252/63/126/20/10), i periodi di ADX e RSI, il
  divisore 40 dell'ADX, l'arrotondamento a un decimale, il tetto di 260 barre.
  Restano in linea di base, misurate e dichiarate.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services import technical_score_service as svc


def _frame(closes: list[float], *, volumi: list[int] | None = None) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": volumi if volumi is not None else [1_000_000] * n,
    })


# ─── 1. Il pavimento di storia ────────────────────────────────────────────


def test_esattamente_trenta_barre_BASTANO_a_calcolare() -> None:
    """`if len(ohlcv) < 30: return None`, col bordo ESCLUSO — trenta barre
    sono abbastanza. Col mutante `< 31` ogni titolo con esattamente trenta
    barre resterebbe senza lente Tecnico, e a schermo «non calcolato» e
    «storia insufficiente» sono la stessa cosa: nulla."""
    assert svc.partial_for(_frame([10.0 + i * 0.1 for i in range(30)])) is not None


def test_ventinove_barre_NON_bastano() -> None:
    """L'altra meta': senza, un `partial_for` che accetta tutto passerebbe."""
    assert svc.partial_for(_frame([10.0 + i * 0.1 for i in range(29)])) is None


# ─── 2. `_ret`: le due guardie sull'indice ────────────────────────────────


def test_un_ritardo_nullo_non_e_un_rendimento() -> None:
    """`if k <= 0 or k >= len(close)`. Col mutante `and` la guardia si apre
    per k=0 e la funzione rende 0.0 — un rendimento FINTO invece di
    «non calcolabile», che a valle entra nella media pesata come un dato."""
    assert svc._ret(pd.Series([10.0, 11.0, 12.0]), 0) is None


def test_un_ritardo_piu_lungo_della_serie_non_e_un_rendimento() -> None:
    """`k >= len(close)`, col bordo INCLUSO: con `>` l'indice `-1-k` esce dalla
    serie e solleva `IndexError` invece di rendere None."""
    s = pd.Series([10.0, 11.0, 12.0])
    assert svc._ret(s, 3) is None


def test_il_ritardo_massimo_utilizzabile_FUNZIONA() -> None:
    """Il bordo dall'altra parte: k = len-1 e' l'ultimo valido e deve rendere
    un numero, altrimenti le due guardie sopra sarebbero vere di niente."""
    s = pd.Series([10.0, 11.0, 12.0])
    assert svc._ret(s, 2) == pytest.approx(0.2)


# ─── 3. Le serie degeneri: nessuna divisione per zero ─────────────────────


def _senza_escursione(n: int = 40, *, volume: int = 1_000) -> pd.DataFrame:
    """Massimo = minimo = chiusura, cioe' escursione NULLA.

    ⚠️ Non e' un'ipotesi di scuola: CLAUDE.md conta 9.216 barre non negoziate
    su 267 titoli, dove il prezzo viene RIPORTATO invece che osservato, e le
    festivita' di un mercato locale ne producono a blocchi."""
    return pd.DataFrame({
        "open": [10.0] * n, "high": [10.0] * n, "low": [10.0] * n,
        "close": [10.0] * n, "volume": [volume] * n,
    })


def test_una_serie_senza_escursione_sta_a_META_della_struttura() -> None:
    """`pos = (price - lo) / rng if rng > 0 else 0.5`, due mutanti in una riga.

    Col `>=` il denominatore e' zero proprio nel caso da cui la guardia
    protegge. E il valore di ripiego e' la META', non un estremo: col mutante
    `1.5` la struttura di ogni titolo fermo leggerebbe 100 — il massimo — cioe'
    «ai massimi del periodo» per un titolo che non si e' mosso."""
    df = _senza_escursione()
    assert svc._structure(df, df["close"]) == pytest.approx(50.0)


def test_volume_interamente_nullo_non_divide_per_zero() -> None:
    """Due guardie nella stessa funzione: `long_avg > 0` e `(upv + dnv) > 0`.
    Coi mutanti `>=` entrambe dividono zero per zero.

    I due valori di ripiego sono NEUTRI (rapporto 1, accumulo 0,5), quindi il
    risultato atteso e' esattamente meta' scala: se un mutante li sposta, il
    volume di un titolo non scambiato smette di leggere «neutro»."""
    df = _senza_escursione(volume=0)
    assert svc._volume(df, df["close"]) == pytest.approx(50.0)


def test_una_serie_piatta_riceve_comunque_un_punteggio(caplog) -> None:
    """⚠️ Questo test e' nato ROSSO e ha trovato un difetto vero.

    L'RSI di una serie perfettamente piatta e' tutto NaN (guadagni e perdite
    sono entrambi zero), quindi `rsi(...).dropna().iloc[-1]` solleva
    `IndexError` e il `except Exception` di `partial_for` rende None: il titolo
    sparisce dalla lente Tecnico invece di ricevere un momento neutro.

    Il guardiano che sembrava coprirlo — `if n > 15 else 50.0` — non poteva:
    `_momentum` e' chiamata solo da `partial_for`, che sbarra sotto le 30
    barre, quindi `n > 15` e' SEMPRE vero e quel ripiego e' codice morto. La
    riga del MACD due righe sotto lo fa nel modo giusto (`if hd.size`), cioe'
    guardando se la serie ripulita e' vuota invece di contare le barre."""
    p = svc.partial_for(_senza_escursione())
    assert p is not None, "una serie piatta non deve far sparire il titolo"
    for chiave in ("trend", "momentum", "structure", "volume"):
        assert 0.0 <= p[chiave] <= 100.0, f"{chiave} fuori scala: {p[chiave]}"
    assert p["momentum"] == pytest.approx(50.0, abs=1.0)


# ─── 4. La percentile trasversale e il titolo giusto ──────────────────────


def test_due_titoli_ricevono_gli_ESTREMI_della_percentile(db) -> None:
    """`rank[sid] = i / (m - 1) * 100 if m > 1 else 50`.

    Col mutante `m > 2` servirebbero TRE titoli perche' la percentile esista:
    con due, entrambi leggerebbero 50 — cioe' «nella media» per un titolo che
    e' il migliore del confronto e per quello che e' il peggiore.

    ⚠️ Il test esistente asserisce `ts_up.rel_strength > ts_dn.rel_strength`,
    che e' la forma giusta per un punteggio ma non distingue 0/100 da 50/50
    piu' un epsilon. Qui si fissano gli ESTREMI, che sono il contratto della
    percentile: il primo e' 0, l'ultimo e' 100."""
    from app.models import Stock, TechnicalScore

    su = Stock(ticker="ZUP", exchange="NASDAQ", name="Su", country="US")
    giu = Stock(ticker="ZDN", exchange="NASDAQ", name="Giu", country="US")
    db.add_all([su, giu])
    db.flush()
    p_su = svc.partial_for(_frame([100.0 + i for i in range(120)]))
    p_giu = svc.partial_for(_frame([300.0 - i for i in range(120)]))
    assert svc.finalize(db, {su.id: p_su, giu.id: p_giu}) == 2
    db.commit()

    assert db.get(TechnicalScore, giu.id).rel_strength == pytest.approx(0.0)
    assert db.get(TechnicalScore, su.id).rel_strength == pytest.approx(100.0)


def test_il_ricalcolo_di_un_titolo_tocca_QUEL_titolo(db) -> None:
    """`select(TechnicalScore).where(TechnicalScore.stock_id == stock_id)`, due
    volte in `recompute_one` — per rileggere la percentile precedente e per
    restituire la riga scritta.

    Col mutante `!=` entrambe pescherebbero la riga di UN ALTRO titolo: la
    percentile di un titolo finirebbe nel composito di un altro, e il pulsante
    «aggiorna» restituirebbe il punteggio del vicino. Nessun errore, due numeri
    verosimili.

    ⚠️ Serve un SECONDO titolo con una riga gia' scritta, altrimenti il
    mutante non ha niente da pescare e il test e' vero di niente."""
    from datetime import UTC, date, datetime, timedelta

    from app.models import OhlcvDaily, Stock, TechnicalScore

    def _con_storia(tk: str, base: float) -> Stock:
        s = Stock(ticker=tk, exchange="NASDAQ", name=tk, country="US")
        db.add(s)
        db.flush()
        avvio = date.today() - timedelta(days=150)
        for i in range(150):
            p = base + i * 0.5
            db.add(OhlcvDaily(stock_id=s.id, date=avvio + timedelta(days=i),
                              open=p, high=p + 1, low=p - 1, close=p, volume=1000.0))
        return s

    mio = _con_storia("MIO", 100.0)
    altro = _con_storia("ALT", 100.0)
    # L'altro titolo porta una percentile RICONOSCIBILE: se il ricalcolo la
    # legge, il composito del mio ne risulta contaminato.
    db.add(TechnicalScore(stock_id=altro.id, composite=50.0, trend=50.0,
                          momentum=50.0, structure=50.0, volume=50.0,
                          rel_strength=99.0, posture="Neutro",
                          computed_at=datetime.now(UTC), breakdown="{}"))
    db.commit()

    riga = svc.recompute_one(db, mio.id)
    assert riga is not None
    assert riga.stock_id == mio.id
    # Nessuna riga precedente per il mio titolo -> percentile neutra 50, non 99.
    assert riga.rel_strength == pytest.approx(50.0)


# ─── 5. La postura: tre bande, un solo proprietario ───────────────────────


@pytest.mark.parametrize(
    ("composito", "atteso"),
    [
        (100.0, "Forte"),
        (66.0, "Forte"),    # il bordo e' INCLUSO
        (65.9, "Neutro"),
        (40.0, "Neutro"),   # idem
        (39.9, "Debole"),
        (0.0, "Debole"),
    ],
)
def test_le_tre_bande_di_postura_hanno_il_bordo_INCLUSO(
    composito: float, atteso: str
) -> None:
    """`>= 66` e `>= 40`, non `>`.

    ⚠️ Il test fissa il COMPORTAMENTO del confine, non le due soglie: sposta i
    valori e i casi si spostano con loro. Cio' che non deve poter cambiare in
    silenzio e' che il bordo sia incluso, che le bande siano ordinate e che
    siano esaustive — un composito non puo' restare senza postura, e la colonna
    e' `nullable=False`."""
    assert svc._posture(composito) == atteso


def test_il_lotto_e_il_pulsante_aggiorna_dicono_la_STESSA_postura(db) -> None:
    """L'invariante che la duplicazione aveva messo a rischio.

    `finalize` (ricalcolo di lotto, a fine scansione) e `recompute_one` (il
    pulsante «aggiorna» della scheda) calcolavano composito e postura con due
    copie identiche dello stesso blocco. Identiche finche' qualcuno non ne
    tocca una: e questa funzione ha gia' reso 500 per mesi proprio cosi'.

    Ora c'e' un proprietario unico, quindi l'invariante e' strutturale — ma il
    test resta, perche' cio' che va impedito e' che la copia RITORNI."""
    from datetime import date, timedelta

    from app.models import OhlcvDaily, Stock, TechnicalScore

    s = Stock(ticker="UGU", exchange="NASDAQ", name="Uguale", country="US")
    db.add(s)
    db.flush()
    avvio = date.today() - timedelta(days=150)
    for i in range(150):
        p = 100.0 + i * 0.5
        db.add(OhlcvDaily(stock_id=s.id, date=avvio + timedelta(days=i),
                          open=p, high=p + 1, low=p - 1, close=p, volume=1000.0))
    db.commit()

    ohlcv = pd.DataFrame({
        "open": [100.0 + i * 0.5 for i in range(150)],
        "high": [101.0 + i * 0.5 for i in range(150)],
        "low": [99.0 + i * 0.5 for i in range(150)],
        "close": [100.0 + i * 0.5 for i in range(150)],
        "volume": [1000] * 150,
    })
    svc.finalize(db, {s.id: svc.partial_for(ohlcv)})
    db.commit()
    da_lotto = db.get(TechnicalScore, s.id)
    composito_lotto, postura_lotto = da_lotto.composite, da_lotto.posture

    db.expire_all()
    da_pulsante = svc.recompute_one(db, s.id)
    assert da_pulsante is not None
    assert da_pulsante.composite == pytest.approx(composito_lotto)
    assert da_pulsante.posture == postura_lotto
