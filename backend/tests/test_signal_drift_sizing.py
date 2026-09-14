"""Il monitor di drift deve dimensionare come il cubo, e saper dire «non lo so».

FA-053. `compute_signal_drift` metteva `n` — il numero di RIGHE — dentro
l'intervallo di Wilson e dentro la soglia `min_n`. Sul magazzino vivo questo
teneva accesi tre allarmi su undici detector, e tutti e tre erano falsi per due
ragioni diverse:

  candle_reversal   n=1372 righe ma 12 finestre indipendenti   37,2% vs base 49,0%
  macd_divergence   n= 170 righe ma  2 finestre                78,2% vs base 51,0%
  hidden_divergence n=  55 righe ma  2 finestre                67,3% vs base 48,0%

⚠️ E c'e' un'aritmetica che va DICHIARATA, non aggirata: con una finestra di 90
giorni il tetto delle finestre indipendenti e' 12 a orizzonte 5 giorni e 3 a 21.
Nessun detector puo' superare `min_n=30`. La correzione giusta non e' abbassare
la soglia finche' qualcosa passa — e' smettere di chiamare «stabile» cio' che e'
semplicemente non misurabile.

Il danno vero del vecchio comportamento non era l'allarme sbagliato: era che
tutto cio' che non veniva segnalato leggeva `direction="stable"`, cioe'
**l'assenza di prova si presentava come prova di stabilita'**.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.models import Alert, SignalOutcome, Stock
from app.services import signal_drift_service as sds
from app.services.detector_performance_service import independent_blocks
from app.stats import sizing


def _seed(db, *, detector: str, dates: list[date], hits: list[int],
          horizon: int = 5) -> None:
    """Un Alert VERO per ogni esito: `signal_outcomes.alert_id` non e'
    nullable, ed e' un vincolo che un helper distratto scopre in fondo."""
    s = db.execute(
        __import__("sqlalchemy").select(Stock).where(Stock.ticker == "DRIFT")
    ).scalars().first()
    if s is None:
        s = Stock(ticker="DRIFT", exchange="NASDAQ", name="Drift", country="US")
        db.add(s)
        db.flush()
    for d, h in zip(dates, hits, strict=True):
        a = Alert(stock_id=s.id, trigger_price=10.0, signal_date=d,
                  signal_name=detector, snapshot=json.dumps({"tone": "bull"}),
                  triggered_at=datetime.now(UTC))
        db.add(a)
        db.flush()
        db.add(SignalOutcome(
            alert_id=a.id, stock_id=s.id, detector=detector, signal_date=d,
            tone="bull", horizon_days=horizon, entry_close=10.0,
            forward_close=11.0, fwd_return=0.1, abs_hit=h,
        ))
    db.flush()


def _oggi_meno(n: int) -> date:
    return date.today() - timedelta(days=n)


# ─── 1. La proprieta' da cui dipende tutto il resto ───────────────────────


def test_il_modulo_di_dimensionamento_non_ha_dipendenze() -> None:
    """⚠️ Solo un modulo FOGLIA e' importabile da entrambi i consumatori.

    Le primitive vivevano dentro i servizi — `wilson_interval` nel drift,
    `independent_blocks` nel cubo, e il cubo importava il primo dal drift —
    quindi il drift non poteva importare le finestre indipendenti senza
    chiudere un ciclo. Non poteva, quindi non lo faceva, quindi misurava
    peggio. Se qualcuno aggiunge qui un import di `app.services` o di
    SQLAlchemy, il ciclo torna possibile e il difetto si riapre da solo.

    Si legge l'AST e non le righe: la prima versione di un test equivalente in
    `test_periodi_indicatori.py` cercava le righe che iniziano con «import» e
    trovava un falso positivo dentro la propria docstring."""
    albero = ast.parse(
        (Path(sizing.__file__)).read_text(encoding="utf-8")
    )
    moduli = sorted(
        {a.name.split(".")[0] for n in ast.walk(albero)
         if isinstance(n, ast.Import) for a in n.names}
        | {(n.module or "").split(".")[0] for n in ast.walk(albero)
           if isinstance(n, ast.ImportFrom)}
    )
    consentiti = {"__future__", "math", "collections", "datetime"}
    assert set(moduli) <= consentiti, f"sizing.py ha acquisito dipendenze: {moduli}"


def test_il_drift_e_il_cubo_usano_LO_STESSO_conteggio(db) -> None:
    """Il criterio di parita' che FA-053 chiede. Due moduli che rispondono alla
    stessa domanda con numeri diversi sono peggio di uno solo che sbaglia: chi
    legge non sa quale credere."""
    dates = [_oggi_meno(60 - i) for i in range(20)]
    _seed(db, detector="candle_reversal", dates=dates, hits=[1] * 20)
    db.commit()

    (riga,) = [r for r in sds.compute_signal_drift(db)
               if r["detector"] == "candle_reversal"]
    assert riga["effective_n"] == independent_blocks(dates, riga["horizon_days"])
    assert riga["effective_n"] == sizing.independent_blocks(dates, riga["horizon_days"])


# ─── 2. Le righe non sono estrazioni indipendenti ─────────────────────────


def test_le_finestre_indipendenti_sono_MENO_delle_righe(db) -> None:
    """Venti scatti in venti giorni consecutivi, etichettati a 5 sedute in
    avanti: condividono quasi tutta la finestra. Il conteggio efficace deve
    crollare, e il numero di righe resta a schermo perche' e' informativo."""
    dates = [_oggi_meno(40 - i) for i in range(20)]
    _seed(db, detector="candle_reversal", dates=dates, hits=[1] * 20)
    db.commit()

    (riga,) = [r for r in sds.compute_signal_drift(db)
               if r["detector"] == "candle_reversal"]
    assert riga["n_matured"] == 20
    assert riga["effective_n"] < riga["n_matured"]
    assert riga["effective_n"] >= 1


def test_un_campione_agglomerato_NON_si_legge_come_stabile(db) -> None:
    """⚠️ Il difetto vero, e non e' l'allarme sbagliato.

    Col vecchio codice tutto cio' che non veniva segnalato rendeva
    `direction="stable"`. Venti righe che sono quattro finestre non dicono
    nulla sulla stabilita' di un detector, ma la parola a schermo diceva che
    erano stabili — l'assenza di prova presentata come prova."""
    dates = [_oggi_meno(40 - i) for i in range(20)]
    _seed(db, detector="candle_reversal", dates=dates, hits=[1] * 20)
    db.commit()

    (riga,) = [r for r in sds.compute_signal_drift(db, min_n=30)
               if r["detector"] == "candle_reversal"]
    assert riga["drift_flag"] is False
    assert riga["direction"] == "insufficient"
    assert riga["direction"] != "stable"


def test_stabile_si_dice_solo_quando_il_campione_REGGE(db) -> None:
    """L'altra meta' del confine: con abbastanza finestre indipendenti e la
    base dentro la banda, «stabile» torna a essere un'affermazione sostenuta."""
    dates = [_oggi_meno(80 - 8 * i) for i in range(10)]   # 8 giorni di distanza
    _seed(db, detector="candle_reversal", dates=dates, hits=[1, 0] * 5)
    db.commit()

    (riga,) = [r for r in sds.compute_signal_drift(db, min_n=3)
               if r["detector"] == "candle_reversal"]
    assert riga["effective_n"] >= 3
    assert riga["direction"] == "stable"
    assert riga["drift_flag"] is False


def test_un_drift_VERO_viene_ancora_segnalato(db) -> None:
    """Il pavimento. Senza, ogni asserzione sopra sarebbe soddisfatta anche da
    un monitor che non segnala mai piu' niente — che e' il modo in cui una
    correzione di onesta' diventa un cancello spento."""
    dates = [_oggi_meno(80 - 8 * i) for i in range(10)]
    _seed(db, detector="candle_reversal", dates=dates, hits=[1] * 10)  # 100%
    db.commit()

    (riga,) = [r for r in sds.compute_signal_drift(db, min_n=3)
               if r["detector"] == "candle_reversal"]
    assert riga["recent_hit_rate"] == 100.0
    assert riga["drift_flag"] is True
    assert riga["direction"] == "improving"


# ─── 3. Il riepilogo deve poter dire quanti non si sanno ──────────────────


def test_il_riepilogo_conta_i_NON_MISURABILI(db) -> None:
    """Senza questo conteggio l'involucro dice «0 segnalati su 11» e si legge
    come undici detector sani."""
    dates = [_oggi_meno(40 - i) for i in range(20)]
    _seed(db, detector="candle_reversal", dates=dates, hits=[1] * 20)
    db.commit()

    righe = sds.compute_signal_drift(db, min_n=30)
    ris = sds.drift_summary(righe, min_n=30)
    assert ris["n_insufficient"] == 1
    assert ris["n_flagged"] == 0
