"""Il riempimento all'indietro degli ingressi del piano.

Due rami: un alert mai rivisto porta ancora lo snapshot della prima
emissione, quindi i valori si copiano; per uno rivisto l'ATR si ricalcola
dalle barre.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.indicators.atr import atr
from app.models import Alert, OhlcvDaily, Stock
from app.scripts.backfill_plan_inputs import CHIAVE, riempi


def _titolo(db: Session, ticker: str = "AAA") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Corp", country="US")
    db.add(s)
    db.flush()
    return s


def _barre(db: Session, s: Stock, righe: list[tuple[str, float, float, float]]) -> None:
    for d, hi, lo, cl in righe:
        db.add(OhlcvDaily(stock_id=s.id, date=date.fromisoformat(d),
                          open=cl, high=hi, low=lo, close=cl, volume=1000))
    db.flush()


def _serie(prima: str, n: int, larghezza: float) -> list[tuple[str, float, float, float]]:
    """n sedute consecutive di ampiezza fissa: un ATR calcolabile a mano."""
    giorno = date.fromisoformat(prima)
    out = []
    for i in range(n):
        d = giorno.fromordinal(giorno.toordinal() + i)
        out.append((d.isoformat(), 100 + larghezza, 100.0, 100.0 + larghezza / 2))
    return out


def _alert(db: Session, s: Stock, *, prima_emissione: str, snap: dict) -> Alert:
    snap = {"tone": "bull", "first_emitted_at": f"{prima_emissione}T23:30:00+00:00", **snap}
    a = Alert(stock_id=s.id, signal_name="structure_break",
              signal_date=date.fromisoformat(prima_emissione),
              triggered_at=datetime.fromisoformat(prima_emissione).replace(tzinfo=UTC),
              trigger_price=100.0, snapshot=json.dumps(snap))
    db.add(a)
    db.flush()
    return a


def test_un_alert_mai_rivisto_porta_ancora_i_valori_della_prima_emissione(db: Session) -> None:
    """I valori si copiano dallo snapshot: sono gia' quelli giusti."""
    s = _titolo(db)
    _barre(db, s, _serie("2026-05-04", 30, 4.0))
    _alert(db, s, prima_emissione="2026-05-20",
           snap={"atr": 3.5, "horizon": "medium",
                 "invalidation": {"level": 90.0, "reason": "quella vera"}})

    rapporto = riempi(db)
    assert (rapporto["copiati_esatti"], rapporto["atr_ricalcolato"]) == (1, 0)
    snap = json.loads(db.query(Alert).one().snapshot)
    assert snap[CHIAVE] == pytest.approx(3.5)
    assert snap["first_invalidation"] == {"level": 90.0, "reason": "quella vera"}
    assert snap["first_horizon"] == "medium"


def test_un_alert_rivisto_ricalcola_l_ATR_dalla_barra_della_prima_emissione(
    db: Session,
) -> None:
    """⚠️ Il caso MRNA: l'ATR nello snapshot e' quello di DOPO il movimento."""
    s = _titolo(db)
    righe = _serie("2026-05-04", 30, 4.0)
    _barre(db, s, righe)
    _alert(db, s, prima_emissione=righe[20][0],
           snap={"atr": 40.0, "amend_count": 7, "horizon": "short",
                 "invalidation": {"level": 90.0}})

    rapporto = riempi(db)
    assert (rapporto["copiati_esatti"], rapporto["atr_ricalcolato"]) == (0, 1)
    snap = json.loads(db.query(Alert).one().snapshot)

    df = pd.DataFrame(
        [{"high": h, "low": lo, "close": c} for _, h, lo, c in righe[:21]])
    assert snap[CHIAVE] == pytest.approx(float(atr(df, 14).iloc[-1]))
    # ⚠️ E non si inventano invalidazione e orizzonte: la catena originale non
    # esiste piu' e il livello e' un fatto del detector, non delle barre.
    assert "first_invalidation" not in snap
    assert "first_horizon" not in snap


def test_un_first_atr_gia_presente_NON_viene_toccato(db: Session) -> None:
    """Quelli fissati dal motore alla creazione sono una misura: non si
    rimpiazzano con una stima."""
    s = _titolo(db)
    _barre(db, s, _serie("2026-05-04", 30, 4.0))
    _alert(db, s, prima_emissione="2026-05-20",
           snap={"atr": 40.0, "amend_count": 3, CHIAVE: 1.5})

    rapporto = riempi(db)
    assert (rapporto["copiati_esatti"], rapporto["atr_ricalcolato"]) == (0, 0)
    snap = json.loads(db.query(Alert).one().snapshot)
    assert snap[CHIAVE] == pytest.approx(1.5)


def test_il_rapporto_MISURA_la_ricostruzione_invece_di_dichiararla_buona(
    db: Session,
) -> None:
    """Il controllo gira sugli alert mai rivisti, dove la verita' si conosce.

    ⚠️ Senza un alert di controllo il conteggio sarebbe zero e lo scarto None,
    cioe' un rapporto vero di niente: qui se ne semina uno il cui ATR
    conservato combacia con le barre, e uno il cui ATR e' fuori scala.
    """
    s = _titolo(db)
    righe = _serie("2026-05-04", 30, 4.0)
    _barre(db, s, righe)
    df = pd.DataFrame(
        [{"high": h, "low": lo, "close": c} for _, h, lo, c in righe[:21]])
    esatto = float(atr(df, 14).iloc[-1])
    _alert(db, s, prima_emissione=righe[20][0], snap={"atr": esatto})
    _alert(db, s, prima_emissione=righe[20][0], snap={"atr": esatto * 2})

    rapporto = riempi(db)
    assert rapporto["controllo_n"] == 2
    assert rapporto["controllo_oltre_il_5pct"] == 1
    assert rapporto["controllo_scarto_mediano_pct"] is not None
