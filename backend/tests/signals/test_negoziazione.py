"""La guardia sui titoli che non scambiano, o scambiano ancorati a un'offerta.

Misurato il 2026-09-23: la regola avrebbe fermato sei titoli, tutti sotto
un'offerta d'acquisto (Iveco, Beazley, Intertek, Schroders, EA, Catalyst),
sui quali il motore aveva emesso 44 alert; e nel replay decennale i titoli
sospesi davano stop ~0 e medie spostate di quasi un R.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from app.models import Alert, Stock
from app.signals.negoziazione import (
    ATR_MINIMO,
    BARRE_VOLUME,
    PREZZO_FERMO,
    VOLUME_NULLO,
    motivo_non_negoziato,
)
from app.signals.signal_scan_service import evaluate_signals

_VIVI = [1000.0] * 30


# ─── La regola ─────────────────────────────────────────────────────────────

def test_un_titolo_normale_passa() -> None:
    assert motivo_non_negoziato(atr=2.0, prezzo=100.0, volumi=_VIVI) is None


def test_un_prezzo_ancorato_a_un_offerta_non_passa() -> None:
    """Beazley il 2026-09-22: ATR allo 0,17% del prezzo, volume normale.
    Scambia, ma al prezzo dell'offerta: nessuna forma su quella serie e'
    un segnale."""
    assert motivo_non_negoziato(atr=0.17, prezzo=100.0, volumi=_VIVI) == PREZZO_FERMO


def test_la_soglia_e_esclusiva() -> None:
    """Esattamente alla soglia si passa, appena sotto no. Il fuori-di-uno
    piu' comune che esista, fissato qui invece che scoperto dopo."""
    prezzo = 100.0
    assert motivo_non_negoziato(atr=ATR_MINIMO * prezzo, prezzo=prezzo, volumi=_VIVI) is None
    assert motivo_non_negoziato(atr=ATR_MINIMO * prezzo * 0.99, prezzo=prezzo,
                                volumi=_VIVI) == PREZZO_FERMO


def test_un_mese_senza_scambi_e_un_titolo_sospeso() -> None:
    volumi = [1000.0] * 10 + [0.0] * BARRE_VOLUME
    # Anche con un ATR "sano": la sospensione si legge sul volume, perche' un
    # prezzo fermo da poco puo' avere ancora l'ATR di prima.
    assert motivo_non_negoziato(atr=2.0, prezzo=100.0, volumi=volumi) == VOLUME_NULLO


def test_una_seduta_con_scambi_nel_mese_basta() -> None:
    """Controllo negativo del caso sopra: 19 barre vuote e una piena non sono
    una sospensione — una festivita' locale riempita dal fornitore vale una
    barra vuota, non un mese."""
    volumi = [0.0] * (BARRE_VOLUME - 1) + [500.0]
    assert motivo_non_negoziato(atr=2.0, prezzo=100.0, volumi=volumi) is None


def test_contano_solo_le_ultime_barre() -> None:
    """Una sospensione di un anno fa non spegne un titolo che oggi scambia."""
    volumi = [0.0] * 100 + [1000.0] * BARRE_VOLUME
    assert motivo_non_negoziato(atr=2.0, prezzo=100.0, volumi=volumi) is None


def test_un_volume_mancante_non_e_un_volume_nullo() -> None:
    """⚠️ Una fonte senza volumi non dice che il titolo e' fermo: dice che non
    lo sa. Spegnerlo per un dato assente sarebbe una conclusione inventata."""
    volumi = [math.nan] * 30
    assert motivo_non_negoziato(atr=2.0, prezzo=100.0, volumi=volumi) is None


def test_senza_atr_decide_solo_il_volume() -> None:
    """Storia troppo corta per un ATR: la regola sul prezzo non si applica, e
    non per questo il titolo viene fermato."""
    assert motivo_non_negoziato(atr=None, prezzo=100.0, volumi=_VIVI) is None
    assert motivo_non_negoziato(atr=math.nan, prezzo=100.0, volumi=_VIVI) is None


# ─── Nello scan: la guardia viene PRIMA dei detector ───────────────────────

def _serie(*, fermo: bool) -> pd.DataFrame:
    righe = []
    for i in range(40):
        c = 100.0 if fermo else 100.0 + (i % 5)
        escursione = 0.02 if fermo else 2.0
        righe.append({"date": f"2026-04-{(i % 28) + 1:02d}" if i < 28 else f"2026-05-{i - 27:02d}",
                      "open": c, "high": c + escursione, "low": c - escursione,
                      "close": c, "volume": 1000})
    return pd.DataFrame(righe)


@pytest.fixture
def chiamate(monkeypatch) -> list[str]:
    """Una spia sul runner: registra chi ha cercato segnali, e non ne trova."""
    viste: list[str] = []

    def spia(ohlcv, *, db=None, stock=None, ctx=None):
        viste.append(stock.ticker if stock is not None else "?")
        return [], []

    monkeypatch.setattr("app.signals.signal_scan_service.detect_signals_and_setups", spia)
    return viste


def test_su_un_titolo_fermo_i_detector_non_vengono_nemmeno_chiamati(db, chiamate) -> None:
    s = Stock(ticker="FERMO", exchange="LSE", name="Fermo plc", country="GB")
    db.add(s)
    db.flush()

    assert evaluate_signals(db, s, _serie(fermo=True)) == 0
    assert chiamate == [], "la guardia deve precedere i detector, setup compresi"
    assert db.query(Alert).filter(Alert.stock_id == s.id).count() == 0


def test_su_un_titolo_che_scambia_i_detector_vengono_chiamati(db, chiamate) -> None:
    """Controllo negativo: senza, il test sopra passerebbe anche con uno scan
    che non chiama MAI il runner."""
    s = Stock(ticker="VIVO", exchange="NASDAQ", name="Vivo Inc", country="US")
    db.add(s)
    db.flush()

    evaluate_signals(db, s, _serie(fermo=False))
    assert chiamate == ["VIVO"]
