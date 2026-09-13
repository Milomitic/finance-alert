"""I confini del magazzino degli esiti, che nessun test percorreva.

⚠️ Trovati dalla sonda di mutazione: `signal_outcome_service` uccideva 20 dei
suoi 57 mutanti. Il modulo e' la SINGOLA fonte di verita' su se un segnale ha
funzionato — se sbaglia, non solleva un'eccezione: produce un numero
plausibile, e ogni pannello a valle lo mostra con la stessa faccia.

I quattro che contano davvero, e perche':

1. Riga 261, `mkt_excess = excess if tone == 'bull' else -excess` -> `!=`.
   Col mutante il SEGNO dell'abilita' market-neutral si inverte per ogni
   segnale del magazzino: i rialzisti diventano ribassisti e viceversa. E'
   la misura di punta del motore, quella che CLAUDE.md chiama `skill`.
2. Riga 255, `fwd_ret > 0` -> `>=`. Un rendimento esattamente nullo
   diventerebbe un COLPO, per entrambi i toni. Un titolo fermo non e' un
   successo ne' rialzista ne' ribassista.
3. Riga 245, `if fi >= len(cs)` -> `>`. E' il confine di maturazione, cioe'
   la garanzia strutturale di no-look-ahead dichiarata nel docstring del
   modulo: una riga nasce solo quando la barra futura ESISTE.
4. Righe 179-182, la ricorrenza della EMA. Il docstring promette
   «pandas-equivalent» e niente lo verificava: la promessa era una frase.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.models import Alert, OhlcvDaily, SignalOutcome, Stock
from app.services import signal_outcome_service as sos

# ─── 1. `_to_date`: la data che arriva come STRINGA ────────────────────────
#
# ⚠️ CLAUDE.md registra gia' questa asimmetria in un altro modulo: la stessa
# colonna torna `date` da Postgres e `str` da SQLite. Qui il ramo stringa
# esisteva e non era percorso da niente.


def test_una_data_iso_di_dieci_caratteri_viene_letta() -> None:
    """Il caso piu' comune, ed e' il confine: `len(v) >= 10`. Col mutante
    `>= 11` ogni data senza orario viene SCARTATA — cioe' ogni barra sparisce
    e il magazzino si svuota in silenzio."""
    assert sos._to_date("2026-01-01") == date(2026, 1, 1)


def test_un_datetime_iso_viene_troncato_alla_data() -> None:
    """`v[:10]`. Col mutante `v[:11]` la stringa diventa `2026-01-01T`, che
    `fromisoformat` rifiuta: la barra viene persa."""
    assert sos._to_date("2026-01-01T13:45:00") == date(2026, 1, 1)


@pytest.mark.parametrize("valore", [123, None, [], {}, 4.5])
def test_un_valore_non_stringa_e_respinto_SENZA_eccezione(valore: object) -> None:
    """`isinstance(v, str) and len(v) >= 10`. Col mutante `or`, `len()` su un
    intero solleva `TypeError` e fa esplodere l'intera maturazione invece di
    scartare una riga."""
    assert sos._to_date(valore) is None


def test_una_riga_senza_chiusura_viene_scartata_non_convertita() -> None:
    """`dd is not None and c is not None`. Col mutante `or`, una chiusura
    NULL arriva a `float(None)`: `TypeError`."""
    righe = [(1, date(2026, 1, 1), 10.0), (1, date(2026, 1, 2), None)]
    fuori = sos._rows_to_arrays(righe)  # type: ignore[arg-type]
    assert len(fuori[1][1]) == 1


# ─── 2. La EMA causale, che il docstring dichiara «pandas-equivalent» ──────


def test_la_ema_coincide_con_pandas_ewm_adjust_false() -> None:
    """⚠️ Quattro mutanti vivevano dentro questa ricorrenza — il seme
    (`values[0]`), la prima uscita (`out[0]`), l'inizio del ciclo
    (`range(1, ...)`) e il peso (`1 - alpha`). Nessuno li vedeva perche' il
    regime che ne esce e' un'etichetta grossolana bull/bear: un EMA sbagliato
    la sposta solo per le barre vicine alla linea.

    Il riferimento e' pandas, cioe' un'implementazione INDIPENDENTE: e' la
    differenza fra verificare la promessa e ripeterla."""
    v = np.array([10.0, 11.0, 9.0, 12.0, 15.0, 14.0, 13.0, 18.0, 17.0, 20.0])
    atteso = pd.Series(v).ewm(span=5, adjust=False).mean().to_numpy()
    assert np.allclose(sos._ema(v, 5), atteso)


# ─── 3. Il pavimento di titoli per data ───────────────────────────────────


def _universo(n: int, *, horizon: int = 2) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    ds = np.array(
        [date(2026, 1, 1) + timedelta(days=i) for i in range(horizon + 1)], dtype=object
    )
    cs = np.array([10.0, 11.0, 12.0][: horizon + 1], dtype="float64")
    return {i: (ds, cs) for i in range(n)}


def test_esattamente_dieci_titoli_bastano_per_un_riferimento() -> None:
    """`len(v) >= _MIN_UNIVERSE_PER_DATE`, col bordo INCLUSO. Col mutante `>`
    servirebbero undici, e ogni data con esattamente dieci resterebbe senza
    riferimento — cioe' `mkt_neutral_hit` nullo su un pezzo del magazzino,
    che a schermo e' indistinguibile da «non ancora maturato».

    ⚠️ Il test fissa il COMPORTAMENTO del pavimento, non il numero dieci:
    ritararlo resta libero, ignorarlo no."""
    assert sos._universe_fwd_medians(_universo(sos._MIN_UNIVERSE_PER_DATE), 2)


def test_un_titolo_in_meno_del_pavimento_non_fa_un_riferimento() -> None:
    """L'altra meta': senza, un pavimento sempre soddisfatto passerebbe."""
    assert sos._universe_fwd_medians(_universo(sos._MIN_UNIVERSE_PER_DATE - 1), 2) == {}


# ─── 4. Le etichette che finiscono a schermo ──────────────────────────────


def _semina(
    db,
    *,
    closes: list[float],
    sig_idx: int,
    tone: str = "bull",
    altri: int = 0,
    closes_altri: list[float] | None = None,
) -> Alert:
    """Un titolo col segnale, piu' `altri` titoli che formano l'universo.

    ⚠️ Il riferimento market-neutral richiede almeno `_MIN_UNIVERSE_PER_DATE`
    titoli per data: con un titolo solo `mkt_neutral_hit` resta nullo e ogni
    asserzione su di esso sarebbe vera di NIENTE."""
    d0 = date(2026, 1, 1)

    def _titolo(tk: str, cl: list[float]) -> Stock:
        s = Stock(ticker=tk, exchange="NASDAQ", name=tk, country="US")
        db.add(s)
        db.flush()
        for i, c in enumerate(cl):
            db.add(OhlcvDaily(stock_id=s.id, date=d0 + timedelta(days=i),
                              open=c, high=c, low=c, close=c, volume=1_000_000))
        return s

    s = _titolo("SEGN", closes)
    for k in range(altri):
        _titolo(f"UNI{k:02d}", closes_altri if closes_altri is not None else closes)
    a = Alert(
        stock_id=s.id, trigger_price=closes[sig_idx],
        signal_date=d0 + timedelta(days=sig_idx), signal_name="trend_pullback",
        snapshot=json.dumps({"tone": tone, "strength": 70, "probability": 55}),
    )
    db.add(a)
    db.flush()
    db.commit()
    return a


@pytest.mark.parametrize("tono", ["bull", "bear"])
def test_un_rendimento_esattamente_nullo_NON_e_un_colpo(db, monkeypatch, tono: str) -> None:
    """`fwd_ret > 0` / `fwd_ret < 0`, entrambi col bordo ESCLUSO.

    Un titolo fermo non e' un successo rialzista ne' ribassista. Coi mutanti
    `>=` e `<=` lo diventerebbe per TUTTI e due i toni contemporaneamente —
    cioe' il tasso di successo del motore salirebbe senza che nessun segnale
    abbia fatto niente."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    _semina(db, closes=[10.0] * 8, sig_idx=2, tone=tono)
    assert sos.mature_outcomes(db) == 1
    riga = db.execute(select(SignalOutcome)).scalars().one()
    assert riga.fwd_return == 0.0
    assert riga.abs_hit == 0


def test_un_prezzo_esattamente_sulla_ema_e_letto_come_ribassista(db, monkeypatch) -> None:
    """`regime = 'bull' if cs[ti] > ema[ti] else 'bear'`, bordo escluso.

    ⚠️ La scelta e' ARBITRARIA — una serie piatta non e' ne' l'uno ne'
    l'altro. Il test la rende esplicita, non la approva: se un giorno si
    decide che il pari vale 'bull', questo test deve rompersi e costringere a
    dirlo, invece di lasciare che il confine si sposti da solo."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    _semina(db, closes=[10.0] * 8, sig_idx=2)
    sos.mature_outcomes(db)
    assert db.execute(select(SignalOutcome)).scalars().one().regime_at_signal == "bear"


@pytest.mark.parametrize(
    ("tono", "colpo_atteso", "segno"),
    [("bull", 1, 1.0), ("bear", 0, -1.0)],
)
def test_il_segno_dell_eccesso_market_neutral_segue_il_TONO(
    db, monkeypatch, tono: str, colpo_atteso: int, segno: float
) -> None:
    """`mkt_excess = excess if tone == 'bull' else -excess` -> `!=`.

    ⚠️ E' il mutante piu' grave del modulo: col `!=` il segno si inverte per
    OGNI riga del magazzino, e `calibration_map.skill` — la misura che la UI
    presenta come abilita' al netto del mercato — leggerebbe i rialzisti come
    ribassisti. Nessuna eccezione, nessun pannello vuoto: solo numeri
    specchiati.

    Il titolo col segnale sale del 30% mentre l'universo sta fermo, quindi
    l'eccesso grezzo e' positivo e il tono decide il resto."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    _semina(
        db,
        closes=[10.0, 10.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
        sig_idx=2,
        tone=tono,
        altri=12,
        closes_altri=[10.0] * 8,
    )
    assert sos.mature_outcomes(db) == 1
    riga = db.execute(select(SignalOutcome)).scalars().one()
    assert riga.universe_mean_fwd == 0.0
    assert riga.mkt_neutral_excess is not None
    assert riga.mkt_neutral_excess * segno > 0
    assert riga.mkt_neutral_hit == colpo_atteso


def test_pareggiare_il_riferimento_NON_e_battere_il_mercato(db, monkeypatch) -> None:
    """`mkt_hit = 1 if mkt_excess > 0 else 0`, bordo escluso, e i due valori
    sono 0 e 1 e non altro: sono una MEDIA a valle, quindi un 2 al posto di un
    1 gonfierebbe il tasso invece di romperlo."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    _semina(db, closes=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0],
            sig_idx=2, altri=12)
    sos.mature_outcomes(db)
    riga = db.execute(select(SignalOutcome)).scalars().one()
    assert riga.mkt_neutral_excess == 0.0
    assert riga.mkt_neutral_hit == 0


def test_la_barra_futura_deve_ESISTERE_perche_una_riga_nasca(db, monkeypatch) -> None:
    """`if fi >= len(cs): continue`, col bordo INCLUSO.

    E' la garanzia strutturale di no-look-ahead che il docstring del modulo
    dichiara. Segnale a idx 5, orizzonte 3, otto barre: la barra futura
    sarebbe la nona e non esiste."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    _semina(db, closes=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0], sig_idx=5)
    assert sos.mature_outcomes(db) == 0


def test_l_ultima_barra_disponibile_BASTA_a_maturare(db, monkeypatch) -> None:
    """L'altra meta' del confine: senza, una maturazione che non avviene mai
    soddisfarebbe il test precedente."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    _semina(db, closes=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0], sig_idx=4)
    assert sos.mature_outcomes(db) == 1


def test_un_titolo_sotto_il_dollaro_matura_come_gli_altri(db, monkeypatch) -> None:
    """Tre guardie del modulo confrontano un prezzo con ZERO — `entry <= 0`,
    `c0 > 0`, `ema_arr[ti] > 0` — e i mutanti le spostano a UNO.

    ⚠️ Il difetto che ne seguirebbe e' silenzioso e selettivo: ogni titolo
    quotato sotto l'unita' sparirebbe dal magazzino e dal riferimento
    market-neutral, senza un errore da nessuna parte. Il catalogo ne ha (il
    listino di Londra sta in sterline, con valori a una cifra)."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    centesimi = [0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.62, 0.64]
    _semina(db, closes=centesimi, sig_idx=2, altri=12)
    assert sos.mature_outcomes(db) == 1
    riga = db.execute(select(SignalOutcome)).scalars().one()
    assert riga.entry_close == 0.54
    assert riga.regime_at_signal is not None
    assert riga.mkt_neutral_hit is not None


def test_commit_False_non_scrive_davvero(db, monkeypatch) -> None:
    """`if commit and added` -> `or`. Col mutante la scrittura viene
    confermata anche quando il chiamante ha chiesto di non farlo: il
    ripopolamento una-tantum perderebbe la possibilita' di annullare."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    _semina(db, closes=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0], sig_idx=2)
    assert sos.mature_outcomes(db, commit=False) == 1
    db.rollback()
    assert db.execute(select(SignalOutcome)).scalars().all() == []


# ─── 5. Le due popolazioni: chi entra nel riferimento ─────────────────────


def test_mature_outcomes_CHIEDE_il_riferimento_senza_ETF(db, monkeypatch) -> None:
    """`_load_universe_closes(..., exclude_etf=True)` al punto di CHIAMATA.

    ⚠️ `test_etf_exclusions.py` verifica gia' che il caricatore sappia
    escludere gli ETF, e che la riga scritta valga quanto il riferimento
    senza ETF. Ma in quella configurazione i due riferimenti sono lo STESSO
    NUMERO — il test lo dice da solo, ed e' corretto: la mediana e' robusta a
    una serie estrema. Quindi la seconda asserzione non distingue una
    `mature_outcomes` che chiede l'esclusione da una che non la chiede.

    Qui gli ETF sono la MAGGIORANZA, cosi' la mediana si sposta davvero: con
    l'esclusione il riferimento e' 0, senza e' +50%."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 2)
    monkeypatch.setattr(sos, "_MIN_UNIVERSE_PER_DATE", 3)
    d0 = date(2026, 1, 1)

    def _titolo(tk: str, cl: list[float], tipo: str | None = None) -> Stock:
        s = Stock(ticker=tk, exchange="NASDAQ", name=tk, country="US",
                  instrument_type=tipo)
        db.add(s)
        db.flush()
        for i, c in enumerate(cl):
            db.add(OhlcvDaily(stock_id=s.id, date=d0 + timedelta(days=i),
                              open=c, high=c, low=c, close=c, volume=1_000))
        return s

    piatto = [10.0, 10.0, 10.0, 10.0]
    for k in range(4):
        _titolo(f"EQ{k}", piatto)
    s = _titolo("SEGN", piatto)
    # Sei ETF che rendono +50% sull'orizzonte: in maggioranza, spostano la
    # mediana dell'intero universo da 0 a +0,5.
    for k in range(6):
        _titolo(f"ETF{k}", [10.0, 10.0, 15.0, 15.0], tipo="etf")

    db.add(Alert(stock_id=s.id, trigger_price=10.0, signal_date=d0,
                 signal_name="trend_pullback",
                 snapshot=json.dumps({"tone": "bull", "strength": 70,
                                      "probability": 55})))
    db.commit()

    assert sos.mature_outcomes(db) == 1
    riga = db.execute(select(SignalOutcome)).scalars().one()
    assert riga.universe_mean_fwd == 0.0, "il riferimento ha incluso gli ETF"


def test_una_barra_a_prezzo_zero_non_avvelena_il_riferimento() -> None:
    """`ok = c0 > 0`, col bordo ESCLUSO: una chiusura a zero come base darebbe
    una divisione per zero, cioe' un `inf` dentro la mediana dell'universo.

    ⚠️ Le barre non negoziate esistono in questo catalogo (CLAUDE.md ne conta
    9.216 su 267 titoli). Servono in MAGGIORANZA per spostare una mediana: e'
    il motivo per cui un difetto del genere puo' restare invisibile a lungo."""
    ds = np.array([date(2026, 1, 1) + timedelta(days=i) for i in range(3)], dtype=object)
    buono = (ds, np.array([10.0, 11.0, 12.0]))
    rotto = (ds, np.array([0.0, 11.0, 12.0]))
    universo: dict[int, tuple[np.ndarray, np.ndarray]] = {i: buono for i in range(10)}
    universo.update({100 + i: rotto for i in range(11)})

    with np.errstate(divide="ignore", invalid="ignore"):
        medie = sos._universe_fwd_medians(universo, 2)
    valore = medie[date(2026, 1, 1)]
    assert np.isfinite(valore)
    assert valore == pytest.approx(0.2)


def test_un_prezzo_di_ingresso_a_zero_viene_SALTATO_non_diviso(db, monkeypatch) -> None:
    """`if entry <= 0: continue`, col bordo INCLUSO. Col mutante `<`, una
    chiusura a zero sulla barra del segnale arriva a `fwd_close / entry`:
    l'intera maturazione esplode e nessun esito viene scritto, per nessun
    titolo."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    _semina(db, closes=[10.0, 11.0, 0.0, 13.0, 14.0, 15.0, 16.0, 17.0], sig_idx=2)
    assert sos.mature_outcomes(db) == 0
