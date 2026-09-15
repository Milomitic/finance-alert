"""Un contesto per titolo, e lo stesso risultato di prima (FA-065).

`evaluate_signals` costruiva un `SignalContext` per i propri cancelli (segno del
trend, ATR) e poi chiamava il runner, che ne costruiva un SECONDO dallo stesso
DataFrame — mentre il docstring del runner dichiarava che condividere la
costruzione era il punto. Il difetto non e' di prestazioni, e non va venduto
come tale senza profilazione: due proprietari dello stesso calcolo divergono,
come la riga Tecnico duplicata fra `finalize` e `recompute_one`, che aveva gia'
prodotto un 500 in produzione.

La chiusura chiede parita' numerica verificata: il risultato con il contesto
passato deve essere IDENTICO a quello con il contesto costruito dal runner.
"""

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

from app.models import Stock
from app.signals import runner, signal_scan_service
from app.signals.context import build_context
from app.signals.runner import detect_signals_and_setups

SEMI = [3, 7, 11, 19, 42]


def _serie(seme: int, n: int = 320) -> pd.DataFrame:
    """Una passeggiata aleatoria abbastanza lunga da accendere EMA200 e i
    detector che la leggono. Seminata: il test deve dire la stessa cosa ogni
    volta."""
    rng = np.random.default_rng(seme)
    chiusure = 100 * np.cumprod(1 + rng.normal(0.0004, 0.021, n))
    aperture = chiusure * (1 + rng.normal(0, 0.006, n))
    alti = np.maximum(aperture, chiusure) * (1 + rng.uniform(0, 0.02, n))
    bassi = np.minimum(aperture, chiusure) * (1 - rng.uniform(0, 0.02, n))
    giorni = pd.bdate_range("2025-06-02", periods=n)
    return pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in giorni],
        "open": aperture, "high": alti, "low": bassi, "close": chiusure,
        "volume": rng.integers(300_000, 5_000_000, n),
    })


def _firma(matches, setups) -> str:
    """Una forma confrontabile anche con i NaN, che `==` su float non
    riconosce uguali a se stessi: il `repr` di `nan` e' sempre `nan`."""
    return repr([asdict(m) for m in matches]) + "|" + repr([asdict(s) for s in setups])


@pytest.mark.parametrize("seme", SEMI)
def test_passare_il_contesto_non_cambia_il_risultato(seme):
    ohlcv = _serie(seme)

    da_solo = detect_signals_and_setups(ohlcv)
    col_contesto = detect_signals_and_setups(ohlcv, ctx=build_context(ohlcv))

    assert _firma(*col_contesto) == _firma(*da_solo)


def test_la_parita_non_e_vera_di_niente():
    """⚠️ Il pavimento. Due liste vuote sono uguali, quindi la parita' sopra
    sarebbe verde anche su serie che non accendono un solo detector. Sui semi
    usati deve comparire almeno qualcosa da confrontare."""
    trovati = sum(
        len(m) + len(s) for m, s in (detect_signals_and_setups(_serie(x)) for x in SEMI)
    )
    assert trovati > 0


def test_un_contesto_per_titolo(db, monkeypatch):
    """La proprieta' che FA-065 chiude: una valutazione, UNA costruzione.

    Si conta sostituendo `build_context` in entrambi i moduli che lo importano
    per nome — sostituirlo solo in `app.signals.context` non basterebbe, perche'
    `from ... import build_context` lega il riferimento al momento dell'import.
    """
    chiamate = []
    vero = build_context

    def contato(ohlcv):
        chiamate.append(len(ohlcv))
        return vero(ohlcv)

    monkeypatch.setattr(runner, "build_context", contato)
    monkeypatch.setattr(signal_scan_service, "build_context", contato)
    s = Stock(ticker="CTX", exchange="NASDAQ", name="Contesto", country="US")
    db.add(s)
    db.flush()

    signal_scan_service.evaluate_signals(db, s, _serie(7))

    assert len(chiamate) == 1, f"contesti costruiti: {len(chiamate)}"


def test_chi_non_passa_il_contesto_lo_riceve_costruito(monkeypatch):
    """Il contratto degli altri chiamanti non cambia: senza `ctx` il runner lo
    costruisce da se', come prima."""
    chiamate = []
    vero = build_context
    monkeypatch.setattr(runner, "build_context", lambda o: chiamate.append(1) or vero(o))

    detect_signals_and_setups(_serie(3))

    assert chiamate == [1]
