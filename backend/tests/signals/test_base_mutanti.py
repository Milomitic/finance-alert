"""Le guardie e i bordi dello scorer della Forza, che nessun test percorreva.

⚠️ `app/signals/detectors/base.py` uccideva 21 dei suoi 58 mutanti. E' il
modulo che trasforma i fattori di un detector nel numero che l'utente legge
come «Forza»: un suo difetto non solleva eccezioni, cambia un punteggio.

Questo progetto ha gia' pagato per una lacuna proprio qui. Gli ancoraggi di
`chart_pattern` erano espressi nelle unita' sbagliate per TUTTA la vita del
detector: la mediana dei pattern segnava Forza 10,6 e uno su 1.041 superava il
cancello di emissione, mentre i test asserivano soltanto che il pattern venisse
EMESSO. Un test che non guarda il NUMERO non puo' vedere questa classe di
difetto.

⚠️ E una scoperta del triage, che decide meta' di questo file: **gran parte dei
sopravvissuti e' equivalente per CONTINUITA', e per progetto.** `concave` e'
definita a tratti e il suo docstring lo dichiara — «The tail is continuous at
(a88, 0.88)» — quindi al bordo esatto `x <= a88` e `x < a88` calcolano lo
STESSO numero, perche' il tratto successivo ci arriva. Lo stesso vale per il
ginocchio di `score` (la compressione parte da zero li') e per i punti di
`interp_adjustment`.

Quei mutanti non sono lacune e non sono nemmeno «tollerati»: sono la PROVA che
la curva non ha salti. La mossa onesta non e' ucciderli — e' asserire la
continuita', che e' la proprieta' che li rende equivalenti. I test che lo fanno
qui sotto non uccidono nessun mutante di proposito.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from app.signals.detectors.base import (
    Event,
    SignalMatch,
    _d,
    concave,
    find_after,
    interp_adjustment,
    log_saturate,
    score,
    score_v2,
    soft01,
    trend_maturity_factor,
)

# ─── 1. Le guardie che proteggono da una divisione per zero ───────────────


def test_soft01_respinge_un_riferimento_NULLO() -> None:
    """`if x <= 0 or ref <= 0: return 0.0`, sul termine del riferimento.

    Col mutante `ref < 0` un riferimento pari a zero passa la guardia e
    `x / (x + 0)` vale 1.0: il fattore piu' forte possibile, restituito
    proprio quando la scala rispetto a cui misurarlo NON ESISTE."""
    assert soft01(5.0, 0.0) == 0.0


def test_soft01_respinge_un_valore_NEGATIVO() -> None:
    """`or` -> `and`: con due termini in `and` basta che uno sia positivo per
    superare la guardia. Con x = -5 e ref = 10 la formula rende +2.0 — un
    fattore fuori da [0, 1) che nessun chiamante si aspetta e che nessun
    `clamp01` a valle riporterebbe al posto giusto, perche' e' POSITIVO."""
    assert soft01(-5.0, 10.0) == 0.0


def test_soft01_accetta_valori_SOTTO_l_unita() -> None:
    """Le due soglie sono ZERO, non uno. Coi mutanti `<= 1` ogni fattore in
    (0, 1] verrebbe azzerato — e i fattori di questo motore vivono quasi tutti
    li' dentro, quindi la Forza collasserebbe per l'intero catalogo."""
    assert soft01(0.5, 1.0) > 0.0
    assert soft01(2.0, 0.5) > 0.0


def test_log_saturate_respinge_un_tetto_NULLO() -> None:
    """Stessa forma: col mutante `ceil < 0` un tetto pari a zero passa e
    `log1p(0)` al denominatore e' zero."""
    assert log_saturate(5.0, 0.0) == 0.0


def test_log_saturate_accetta_valori_SOTTO_l_unita() -> None:
    """Le soglie sono zero, non uno."""
    assert log_saturate(0.5, 10.0) > 0.0
    assert log_saturate(5.0, 1.0) > 0.0


def test_concave_respinge_un_ancoraggio_NULLO() -> None:
    """`if x <= 0 or a45 <= 0`. Col mutante `a45 < 0` il primo ancoraggio a
    zero passa la guardia e `x / a45` divide per zero."""
    assert concave(1.0, (0.0, 1.0, 2.0, 3.0)) == 0.0


@pytest.mark.parametrize(
    "ancoraggi",
    [
        (1.0, 1.0, 2.0, 3.0),   # a75 == a45
        (1.0, 2.0, 2.0, 3.0),   # a88 == a75
        (1.0, 2.0, 3.0, 3.0),   # ceil == a88
    ],
)
def test_concave_sopravvive_ad_ancoraggi_DEGENERI(ancoraggi: tuple) -> None:
    """`a75 > a45`, `a88 > a75`, `ceil > a88`: tre guardie contro un
    denominatore nullo, e i mutanti `>=` le spostano dentro il caso da cui
    proteggono.

    ⚠️ Non e' un caso di scuola. Gli ancoraggi sono scritti a mano, un
    detector per volta, in `app/signals/detectors/`: due valori uguali sono un
    refuso plausibile, e col mutante diventerebbero una divisione per zero
    durante una scansione dell'universo."""
    for x in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 10.0):
        y = concave(x, ancoraggi)
        assert 0.0 <= y < 1.0, f"x={x} -> {y}"


# ─── 2. La continuita', che NON uccide mutanti ed e' il punto ─────────────


def test_concave_e_CONTINUA_sui_tre_nodi() -> None:
    """⚠️ Questo test non uccide nessun mutante, di proposito.

    I bordi `x <= a45`, `x <= a75`, `x <= a88` hanno ciascuno un mutante `<`
    che SOPRAVVIVE, e la ragione e' che al bordo esatto il tratto successivo
    calcola lo stesso numero: la curva non ha salti. Sono equivalenti PERCHE'
    vale questa proprieta', non nonostante.

    Quindi la cosa da fissare e' la proprieta'. Se un giorno qualcuno rompe la
    continuita' — cambiando 0,45 o 0,30 o 0,13 senza rifare i conti — quei
    mutanti diventerebbero uccidibili e nessuno se ne accorgerebbe, mentre la
    Forza farebbe un gradino su un bordo."""
    a = (2.0, 5.0, 9.0, 20.0)
    eps = 1e-9
    for nodo in (2.0, 5.0, 9.0):
        sotto, sopra = concave(nodo - eps, a), concave(nodo + eps, a)
        assert math.isclose(sotto, sopra, abs_tol=1e-6), (
            f"salto sul nodo {nodo}: {sotto} -> {sopra}"
        )


def test_il_ginocchio_di_score_e_CONTINUO() -> None:
    """Stessa forma: `if raw > _CONF_KNEE` ha un mutante `>=` che sopravvive
    perche' al ginocchio la compressione parte da zero. Si fissa il fatto che
    il punteggio non salti li'."""
    def punteggio(v: float) -> int:
        return score({"f": v}, {"f": 1.0})

    assert abs(punteggio(0.7199) - punteggio(0.7201)) <= 1


def test_concave_non_raggiunge_MAI_il_suo_asintoto() -> None:
    """L'invariante dichiarata dal modulo: «approaches but never reaches».

    ⚠️ Vale anche per un x mostruoso, dove `exp(-(x-a88)/scale)` va in
    underflow a 0,0 e la curva toccherebbe il tetto esattamente — il commento
    accanto all'epsilon lo spiega, e niente lo verificava."""
    a = (2.0, 5.0, 9.0, 20.0)
    assert concave(1e12, a) < 0.99
    assert concave(1e300, a) < 0.99


# ─── 3. I confini che spostano un risultato ──────────────────────────────


def test_le_bande_di_maturita_cambiano_DOPO_la_soglia_non_SU() -> None:
    """`if age < 60` / `< 120` / `< 250`, col bordo ESCLUSO: a 60 barre il
    trend e' gia' nella banda successiva.

    ⚠️ Si asserisce che il valore CAMBI attraversando la soglia e resti uguale
    subito dopo — non quanto valga. I quattro livelli (0,5 / 0,7 / 1,0 / 0,35)
    vengono da un backtest e ritararli deve restare libero; dove cade il
    confine, no."""
    for soglia in (60, 120, 250):
        assert trend_maturity_factor(soglia - 1) != trend_maturity_factor(soglia)
        assert trend_maturity_factor(soglia) == trend_maturity_factor(soglia + 1)


def test_un_evento_ESATTAMENTE_alla_data_di_partenza_e_escluso() -> None:
    """`if ed <= a: continue`. Il docstring dice «strictly after»: col mutante
    `<` un evento dello stesso giorno diventerebbe una conferma di se' stesso,
    che e' come una catena si auto-conferma."""
    ev = [Event(date="2026-01-10", type="x")]
    assert find_after(ev, "x", after="2026-01-10", within_days=5) is None


def test_un_evento_all_ULTIMO_giorno_della_finestra_e_incluso() -> None:
    """`if (ed - a).days <= within_days`, col bordo INCLUSO: una finestra di
    cinque giorni ne copre cinque. Col mutante ne copre quattro, e le catene
    si accorciano in silenzio."""
    ev = [Event(date="2026-01-15", type="x")]
    assert find_after(ev, "x", after="2026-01-10", within_days=5) is ev[0]


def test_una_data_con_ORARIO_viene_troncata_alla_data() -> None:
    """`_date.fromisoformat(iso[:10])`. Col mutante `[:11]` la stringa diventa
    `2026-01-10T`, che `fromisoformat` rifiuta: l'intera ricerca di eventi
    esplode invece di leggere la data."""
    assert _d("2026-01-10T13:45:00") == date(2026, 1, 10)


def test_score_v2_ignora_una_chiave_di_forza_SENZA_fattore() -> None:
    """`for k in strength_keys if k in weights and k in factors` -> `or`.

    Col mutante basta che la chiave stia in UNO dei due dizionari, quindi
    `factors[k]` solleva `KeyError` su una chiave che esiste solo fra i pesi.
    ⚠️ I detector dichiarano `strength_keys` a mano: una chiave di troppo, o un
    fattore che un ramo non calcola, e la scansione dell'universo si ferma."""
    v = score_v2(
        factors={"a": 0.5},
        weights={"a": 1.0, "b": 1.0},
        strength_keys={"a", "b"},
    )
    assert 0 <= v <= 100


def test_interp_adjustment_confronta_i_VALORI_non_gli_aggiustamenti() -> None:
    """`if raw >= pts[-1][0]`: l'indice 0 e' il valore grezzo, l'indice 1 e'
    l'aggiustamento. Col mutante `pts[-1][1]` il confronto avviene contro
    l'AGGIUSTAMENTO — due colonne diverse della stessa tabella, e il difetto e'
    invisibile finche' i due numeri non divergono."""
    punti = [(0.0, -3.0), (10.0, 6.0)]
    # raw = 7 sta fra i due punti: deve interpolare, non saturare.
    # Col mutante il confronto e' `7 >= 6` -> vero -> renderebbe subito 6.0.
    assert interp_adjustment(7.0, punti) == pytest.approx(-3.0 + 9.0 * 0.7)


# ─── 4. I valori neutri predefiniti ──────────────────────────────────────


def test_un_segnale_non_migrato_nasce_a_forza_ZERO_e_probabilita_50() -> None:
    """I default di `SignalMatch`. La migrazione ai due punteggi e' incrementale
    e il commento accanto lo dice: un detector non ancora migrato deve leggere
    NEUTRO, non «un po' forte».

    ⚠️ Col mutante `strength = 1` ogni segnale non migrato porterebbe una Forza
    inventata; col mutante `probability = 51` la Probabilita' neutra smetterebbe
    di essere neutra — e CLAUDE.md fissa proprio il 50 come il valore a cui
    `calibration_map` degrada quando l'artefatto manca."""
    m = SignalMatch(name="x", tone="bull", signal_date="2026-01-01",
                    chain=[], invalidation=None)
    assert m.strength == 0
    assert m.probability == 50
