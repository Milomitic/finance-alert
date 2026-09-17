"""I sei detector che non emettevano un livello di invalidazione.

Misurato in produzione il 2026-09-17: 8.666 alert, 6.157 con un livello (71%).
Il 29% mancante NON era distribuito a caso — era SEI detector interi a zero,
`squeeze_expansion` (1110 alert), `adx_confirmation` (758), `macd_divergence`
(308), `gap_and_go` (150), `hidden_divergence` (120), `rsi_divergence` (62).
Tutti e sei passavano `invalidation=None` cablato.

Senza livello non c'e' stop, quindi non c'e' piano, quindi nessun esito basato
sul piano: una classifica d'efficacia costruita sul piano avrebbe coperto 11
detector su 17 senza dirlo.

⚠️ Nessuno dei sei livelli e' inventato: cinque sono gia' calcolati dal motore
degli eventi (`breakout.payload["level"]`, `gap.payload["prev_close"]`, i pivot
delle divergenze) e il sesto si legge dalle barre della compressione. Dove il
dato non c'e', il detector NON ripiega su un numero plausibile: resta None. Un
livello fabbricato e' peggio di nessun livello, perche' il piano lo mostrerebbe
con la stessa faccia di uno vero.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.signals.context import build_context
from app.signals.detectors.adx_confirmation import AdxConfirmation
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.gap_and_go import GapAndGo
from app.signals.detectors.hidden_divergence import HiddenDivergence
from app.signals.detectors.macd_divergence import MacdDivergence
from app.signals.detectors.rsi_divergence import RsiDivergence
from app.signals.detectors.squeeze_expansion import SqueezeExpansion
from app.signals.events import Event

CHIUSURA = 100.0


def _data(i: int) -> str:
    return f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}"


def _df(n: int = 40, estremi: dict[str, tuple[float, float]] | None = None) -> pd.DataFrame:
    """Barre piatte a 100, con `estremi` = {data: (low, high)} dove serve.

    Le fixture degli altri test dei detector sono piatte (low 99 / high 101):
    va bene per verificare che un segnale scatti, ma renderebbe DEGENERE un
    test sui livelli — 99 sarebbe insieme il minimo del pivot, il minimo della
    compressione e il minimo di qualunque altra finestra, quindi un livello
    sbagliato combacerebbe con quello giusto.
    """
    estremi = estremi or {}
    righe = []
    for i in range(n):
        d = _data(i)
        lo, hi = estremi.get(d, (99.0, 101.0))
        righe.append({"date": d, "open": CHIUSURA, "high": hi, "low": lo,
                      "close": CHIUSURA, "volume": 1000.0})
    return pd.DataFrame(righe)


def _livello(m: SignalMatch | None) -> float:
    assert isinstance(m, SignalMatch), "il detector non ha prodotto un segnale"
    assert m.invalidation is not None, "nessun livello di invalidazione emesso"
    return float(m.invalidation["level"])


# ─── 1. adx_confirmation: il livello Donchian rotto ────────────────────────

def test_adx_invalida_sul_livello_che_ha_rotto() -> None:
    """Il motore degli eventi mette gia' il livello nel payload del breakout:
    e' il massimo/minimo della finestra superato dalla chiusura. Rientrarci
    dentro e' la definizione di rottura fallita."""
    df = _df()
    eventi = [
        Event("2026-02-10", "adx_trend", "bull", magnitude=0.6,
              payload={"adx": 38.0, "plus_di": 34.0, "minus_di": 12.0}),
        Event("2026-02-10", "breakout", "bull", magnitude=0.04, payload={"level": 97.5}),
    ]
    m = AdxConfirmation().detect(eventi, df, build_context(df))
    assert _livello(m) == 97.5


def test_adx_senza_livello_nel_payload_non_inventa_nulla() -> None:
    df = _df()
    eventi = [
        Event("2026-02-10", "adx_trend", "bull", magnitude=0.6,
              payload={"adx": 38.0, "plus_di": 34.0, "minus_di": 12.0}),
        Event("2026-02-10", "breakout", "bull", magnitude=0.04, payload={}),
    ]
    m = AdxConfirmation().detect(eventi, df, build_context(df))
    assert isinstance(m, SignalMatch)
    assert m.invalidation is None


# ─── 2. gap_and_go: il gap colmato ─────────────────────────────────────────

def test_gap_invalida_quando_il_gap_e_colmato() -> None:
    df = _df()
    eventi = [
        Event("2026-02-10", "gap", "bull", magnitude=0.05,
              payload={"gap_pct": 0.05, "open": 100.0, "prev_close": 95.2, "close": 100.0}),
        Event("2026-02-10", "volume_spike", None, magnitude=3.0, payload={}),
    ]
    m = GapAndGo().detect(eventi, df, build_context(df))
    assert _livello(m) == 95.2


def test_gap_con_payload_parziale_resta_senza_livello() -> None:
    """⚠️ I payload storici non hanno `prev_close` — i test preesistenti di
    questo detector lo dimostrano, passando solo `gap_pct`. Il ripiego corretto
    e' nessun livello, non un livello ricostruito a occhio."""
    df = _df()
    eventi = [
        Event("2026-02-10", "gap", "bull", magnitude=0.05, payload={"gap_pct": 0.05}),
        Event("2026-02-10", "volume_spike", None, magnitude=3.0, payload={}),
    ]
    m = GapAndGo().detect(eventi, df, build_context(df))
    assert isinstance(m, SignalMatch)
    assert m.invalidation is None


# ─── 3. Le tre divergenze: l'estremo del pivot ─────────────────────────────

_DIVERGENZE = [
    (RsiDivergence, "rsi_divergence", {"period": 14, "rsi": [22.0, 42.0]}),
    (MacdDivergence, "macd_divergence", {}),
    (HiddenDivergence, "hidden_divergence", {}),
]


@pytest.mark.parametrize(("classe", "tipo", "extra"), _DIVERGENZE)
def test_la_divergenza_invalida_sull_estremo_del_pivot(classe, tipo, extra) -> None:
    """La divergenza e' un'affermazione SU un estremo di prezzo. Se il prezzo
    va oltre quell'estremo, l'affermazione e' semplicemente falsa — non serve
    scegliere una soglia, la struttura la fornisce."""
    df = _df(estremi={"2026-02-01": (88.5, 101.0)})
    eventi = [Event("2026-02-01", tipo, "bull", magnitude=0.4,
                    payload={**extra, "pivot_dates": ["2026-01-10", "2026-02-01"]})]
    m = classe().detect(eventi, df, build_context(df))
    assert _livello(m) == 88.5


@pytest.mark.parametrize(("classe", "tipo", "extra"), _DIVERGENZE)
def test_la_divergenza_ribassista_invalida_sul_massimo(classe, tipo, extra) -> None:
    df = _df(estremi={"2026-02-01": (99.0, 112.25)})
    payload = {**extra, "pivot_dates": ["2026-01-10", "2026-02-01"]}
    if tipo == "rsi_divergence":
        payload["rsi"] = [78.0, 58.0]
    eventi = [Event("2026-02-01", tipo, "bear", magnitude=0.4, payload=payload)]
    m = classe().detect(eventi, df, build_context(df))
    assert _livello(m) == 112.25


@pytest.mark.parametrize(("classe", "tipo", "extra"), _DIVERGENZE)
def test_la_divergenza_senza_pivot_noti_resta_senza_livello(classe, tipo, extra) -> None:
    df = _df()
    eventi = [Event("2026-02-01", tipo, "bull", magnitude=0.4,
                    payload={**extra, "pivot_dates": ["1999-01-01", "1999-01-02"]})]
    m = classe().detect(eventi, df, build_context(df))
    assert isinstance(m, SignalMatch)
    assert m.invalidation is None


# ─── 4. squeeze_expansion: il lato opposto della compressione ──────────────

def test_squeeze_invalida_rientrando_nella_compressione() -> None:
    """Il segnale dice «l'energia accumulata si e' rilasciata in su». Tornare
    sotto il pavimento della compressione dice che non era un rilascio."""
    df = _df(estremi={"2026-01-15": (93.75, 101.0)})
    eventi = [
        Event("2026-01-10", "bb_squeeze", None, magnitude=1.4, payload={"period": 20}),
        Event("2026-01-20", "bb_expansion", "bull", magnitude=0.05, payload={"period": 20}),
    ]
    m = SqueezeExpansion().detect(eventi, df, build_context(df))
    assert _livello(m) == 93.75


def test_squeeze_ribassista_invalida_sul_tetto_della_compressione() -> None:
    df = _df(estremi={"2026-01-15": (99.0, 108.5)})
    eventi = [
        Event("2026-01-10", "bb_squeeze", None, magnitude=1.4, payload={"period": 20}),
        Event("2026-01-20", "bb_expansion", "bear", magnitude=0.05, payload={"period": 20}),
    ]
    m = SqueezeExpansion().detect(eventi, df, build_context(df))
    assert _livello(m) == 108.5


def test_squeeze_prende_le_barre_DELLA_compressione_non_tutta_la_storia() -> None:
    """⚠️ Il minimo piu' basso e' FUORI dalla finestra di compressione: se
    l'implementazione leggesse tutto lo storico prenderebbe 70.0, cioe' uno
    stop enorme su un livello che col segnale non c'entra niente."""
    df = _df(estremi={"2026-01-15": (93.75, 101.0), "2026-02-05": (70.0, 101.0)})
    eventi = [
        Event("2026-01-10", "bb_squeeze", None, magnitude=1.4, payload={"period": 20}),
        Event("2026-01-20", "bb_expansion", "bull", magnitude=0.05, payload={"period": 20}),
    ]
    m = SqueezeExpansion().detect(eventi, df, build_context(df))
    assert _livello(m) == 93.75


# ─── 5. La proprieta' trasversale ──────────────────────────────────────────

def _tutti_i_sei_bull() -> list[tuple[str, SignalMatch | None]]:
    df_piv = _df(estremi={"2026-02-01": (88.5, 101.0)})
    df_sq = _df(estremi={"2026-01-15": (93.75, 101.0)})
    df = _df()
    casi: list[tuple[str, SignalMatch | None]] = [
        ("adx_confirmation", AdxConfirmation().detect([
            Event("2026-02-10", "adx_trend", "bull", magnitude=0.6,
                  payload={"adx": 38.0, "plus_di": 34.0, "minus_di": 12.0}),
            Event("2026-02-10", "breakout", "bull", magnitude=0.04, payload={"level": 97.5}),
        ], df, build_context(df))),
        ("gap_and_go", GapAndGo().detect([
            Event("2026-02-10", "gap", "bull", magnitude=0.05,
                  payload={"gap_pct": 0.05, "open": 100.0, "prev_close": 95.2, "close": 100.0}),
            Event("2026-02-10", "volume_spike", None, magnitude=3.0, payload={}),
        ], df, build_context(df))),
        ("squeeze_expansion", SqueezeExpansion().detect([
            Event("2026-01-10", "bb_squeeze", None, magnitude=1.4, payload={"period": 20}),
            Event("2026-01-20", "bb_expansion", "bull", magnitude=0.05, payload={"period": 20}),
        ], df_sq, build_context(df_sq))),
    ]
    for classe, tipo, extra in _DIVERGENZE:
        casi.append((tipo, classe().detect(
            [Event("2026-02-01", tipo, "bull", magnitude=0.4,
                   payload={**extra, "pivot_dates": ["2026-01-10", "2026-02-01"]})],
            df_piv, build_context(df_piv))))
    return casi


def test_tutti_e_sei_emettono_un_livello() -> None:
    mancanti = [nome for nome, m in _tutti_i_sei_bull()
                if not isinstance(m, SignalMatch) or m.invalidation is None]
    assert not mancanti, f"ancora senza livello: {mancanti}"


def test_il_livello_sta_dalla_parte_che_fa_perdere() -> None:
    """⚠️ Un livello dal lato SBAGLIATO non si denuncia da solo.

    `buildPlaybook` calcola `structDist = |entry - stop|` e poi ripiazza lo stop
    dalla parte giusta: un livello sopra il prezzo su un segnale rialzista non
    produce quindi un errore ne' uno stop assurdo — produce uno stop con la
    DISTANZA sbagliata, cioe' un piano dall'aria perfettamente sana. E la
    distanza e' cio' che dimensiona la posizione.
    """
    for nome, m in _tutti_i_sei_bull():
        livello = _livello(m)
        assert livello < CHIUSURA, (
            f"{nome}: invalidazione rialzista a {livello} SOPRA il prezzo {CHIUSURA}"
        )


def test_ogni_livello_porta_una_ragione_leggibile() -> None:
    """La ragione finisce a schermo nel piano, accanto allo stop. Un livello
    senza spiegazione e' un numero che l'utente non puo' giudicare."""
    for nome, m in _tutti_i_sei_bull():
        assert isinstance(m, SignalMatch) and m.invalidation is not None
        ragione = m.invalidation.get("reason")
        assert isinstance(ragione, str) and len(ragione) > 8, f"{nome}: ragione assente"
