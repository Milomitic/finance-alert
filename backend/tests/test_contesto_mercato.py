"""Le fonti di mercato del contesto d'emissione (FA-150)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.services import contesto_mercato_service as cm

D0 = date(2026, 1, 5)


def _serie(chiusure: list[float], fine: date) -> tuple[np.ndarray, np.ndarray]:
    ds = np.array([fine - timedelta(days=len(chiusure) - 1 - i) for i in range(len(chiusure))],
                  dtype=object)
    return ds, np.asarray(chiusure, dtype=float)


def test_il_rendimento_di_mercato_e_la_mediana_con_la_soglia_di_titoli() -> None:
    serie = {k: _serie([100.0, 100.0 * (1 + k / 100)], D0) for k in range(11)}
    out = cm.rendimenti_mediani(serie)
    assert list(out) == [D0] and abs(out[D0] - 0.05) < 1e-12
    pochi = {k: v for k, v in serie.items() if k < 9}
    assert cm.rendimenti_mediani(pochi) == {}


def test_la_mediana_di_settore_esclude_settori_piccoli_e_titoli_fermi() -> None:
    def lineare(fine_ret: float, fine: date) -> tuple[np.ndarray, np.ndarray]:
        c = list(np.linspace(100.0, 100.0 * (1 + fine_ret), 70))
        return _serie(c, fine)

    serie = {k: lineare(0.01 * k, D0) for k in range(5)}            # tecnologia
    serie[10] = lineare(0.5, D0)                                     # finanza, da solo
    serie[11] = lineare(9.0, D0 - timedelta(days=60))                # tecnologia, fermo
    settori = {k: "Tecnologia" for k in range(5)} | {10: "Finanza", 11: "Tecnologia"}
    out = cm.mediane_di_settore(serie, settori)
    assert set(out) == {"Tecnologia"}
    attesa = float(np.median([serie[k][1][-1] / serie[k][1][-64] - 1 for k in range(5)]))
    assert out["Tecnologia"] == attesa


def test_costruisci_legge_il_catalogo_senza_gli_etf(db) -> None:
    from app.models import OhlcvDaily, Stock

    oggi = date(2026, 3, 31)
    for k in range(12):
        s = Stock(ticker=f"M{k}", exchange="NYSE", name=f"M {k}", country="US",
                  sector="Industria", instrument_type="etf" if k == 11 else "stock")
        db.add(s)
        db.flush()
        for i in range(80):
            c = 100.0 * (1 + 0.001 * k) ** i
            db.add(OhlcvDaily(stock_id=s.id, date=oggi - timedelta(days=79 - i), open=c,
                              high=c, low=c, close=c, volume=1e6))
    db.commit()
    m = cm.costruisci(db, oggi=oggi)
    # Undici societa' (l'ETF fuori): la mediana e' il titolo k=5.
    assert abs(m.rendimenti[oggi] - 0.005) < 1e-9
    assert set(m.rs63_settore) == {"Industria"}
