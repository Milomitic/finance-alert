"""I confini dei setup, che nessun test percorreva.

⚠️ `setup_service` uccideva 49 dei suoi 90 mutanti. E' il modulo dei segnali
«in formazione»: decide chi entra nella lista, chi ne esce, e quanto anticipo
il prodotto dichiara di aver dato — cioe' il numero che giustifica l'esistenza
della funzione.

Due cose emerse dal triage, e nessuna delle due era «scrivere il test
mancante»:

1. Il file conteneva DUE mediane, e non erano duplicati: quella annidata in
   `conversion_stats` NON ordinava. Funzionava perche' il chiamante passava
   l'elenco gia' ordinato venti righe sopra — la sua correttezza dipendeva da
   qualcun altro e niente lo diceva. Su un elenco non ordinato rispondevano 30
   contro 7. Ora ce n'e' una sola, e ordina.
2. `_median_of` dichiarava `-> float | None` e nel caso DISPARI restituiva
   l'int ricevuto. Un'annotazione vera meta' delle volte e' peggio di nessuna,
   perche' chi legge smette di controllare.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services import setup_service as ss

# ─── 1. La mediana ────────────────────────────────────────────────────────


def test_la_mediana_ORDINA_da_sola() -> None:
    """⚠️ Il test che la seconda mediana non aveva.

    Gli anticipi arrivano dalla query in un ordine qualsiasi; la mediana non
    puo' dipendere da chi la chiama. Su questo elenco la versione che non
    ordinava rispondeva 30 — il massimo — invece di 7."""
    assert ss._median_of([14, 2, 30, 1, 7]) == 7.0


def test_la_mediana_pari_e_la_MEDIA_dei_due_centrali() -> None:
    """`(ys[mid - 1] + ys[mid]) / 2.0`: i mutanti spostano l'indice a `mid - 2`
    e il divisore a 3, e in entrambi i casi il numero resta plausibile."""
    assert ss._median_of([1, 2, 3, 4]) == 2.5


def test_la_mediana_dispari_e_l_elemento_CENTRALE() -> None:
    """`mid = len(ys) // 2`: col mutante `// 3` l'indice scivola verso il basso
    e la «mediana» diventa un quantile qualsiasi — su cinque elementi il
    secondo invece del terzo."""
    assert ss._median_of([10, 20, 30, 40, 50]) == 30.0


def test_la_mediana_e_SEMPRE_un_float() -> None:
    """L'annotazione dice `float | None` e ora e' vera anche nel caso dispari.
    ⚠️ Non e' pignoleria: `median_lead_days` finisce in JSON, e un 7 e un 7.0
    si leggono diversamente a schermo."""
    assert isinstance(ss._median_of([1, 2, 3]), float)
    assert isinstance(ss._median_of([1, 2, 3, 4]), float)


def test_la_mediana_di_NIENTE_e_None_non_zero() -> None:
    """Un elenco vuoto non ha mediana. Zero sarebbe un valore, e a schermo
    «anticipo mediano 0 giorni» direbbe che il prodotto non anticipa niente —
    la stessa regola di onesta' per cui il tasso di conversione e' None e non
    0% finche' nulla si e' risolto."""
    assert ss._median_of([]) is None


# ─── 2. Il sommario dei rendimenti ────────────────────────────────────────


def _esito(giorno: date, *, colpo: int | None, eccesso: float | None = 0.01,
           rendimento: float = 0.02, orizzonte: int = 1):
    return SimpleNamespace(
        signal_date=giorno, horizon_days=orizzonte, mkt_neutral_hit=colpo,
        mkt_neutral_excess=eccesso, fwd_return=rendimento,
    )


def _distanziati(n: int, colpi: int):
    d0 = date(2026, 1, 1)
    return [_esito(d0 + timedelta(days=10 * i), colpo=1 if i < colpi else 0)
            for i in range(n)]


def test_il_tasso_conta_i_COLPI_non_il_complemento() -> None:
    """`sum(1 for o in judged if o.mkt_neutral_hit == 1)` -> `!=`.

    Col mutante il conteggio passa ai NON colpi e il tasso si specchia: 30%
    diventa 70% e viceversa. Nessun errore, nessun pannello vuoto — solo il
    numero che decide se un setup «funziona», con il segno rovesciato."""
    s = ss._return_summary(_distanziati(10, 3))
    assert s["converted_hit_rate"] == pytest.approx(30.0)


def test_gli_esiti_senza_giudizio_non_entrano_nel_tasso() -> None:
    """`judged = [o for o in outcomes if o.mkt_neutral_hit is not None]`.

    ⚠️ Un esito senza riferimento di mercato non e' un fallimento: e' assente.
    Contarlo come zero abbasserebbe il tasso in proporzione a quanti giorni non
    hanno un riferimento — cioe' misurerebbe la copertura dei dati e la
    chiamerebbe efficacia."""
    righe = _distanziati(4, 2) + [_esito(date(2026, 6, 1), colpo=None)]
    s = ss._return_summary(righe)
    assert s["converted_judged"] == 4
    assert s["converted_hit_rate"] == pytest.approx(50.0)


def test_il_campione_e_scarso_SOTTO_la_soglia_non_SU() -> None:
    """`"converted_low_confidence": eff_n < _DEFAULT_MIN_N`, bordo escluso.

    Con esattamente `_DEFAULT_MIN_N` finestre indipendenti il campione NON e'
    scarso. ⚠️ Come nel cubo dei detector, la pastiglia oggi e' accesa quasi
    sempre: proprio per questo il bordo va fissato, perche' un flag sempre
    acceso non si distingue da un flag rotto."""
    from app.services.detector_performance_service import _DEFAULT_MIN_N

    n = _DEFAULT_MIN_N
    al_bordo = ss._return_summary(_distanziati(n, n // 2))
    assert al_bordo["converted_effective_n"] == n
    assert al_bordo["converted_low_confidence"] is False
    sotto = ss._return_summary(_distanziati(n - 1, (n - 1) // 2))
    assert sotto["converted_low_confidence"] is True


def test_gli_estremi_dell_intervallo_non_sono_SCAMBIATI() -> None:
    """`"converted_ci_low": ci[0]` -> `ci[1]`.

    Col mutante l'estremo alto viene presentato come quello basso, quindi
    l'intervallo si legge rovesciato — e un intervallo il cui «minimo» supera
    il suo «massimo» e' proprio la forma che un lettore attento userebbe per
    accorgersene, se solo qualcuno gliela mostrasse coerente."""
    s = ss._return_summary(_distanziati(20, 14))
    assert s["converted_ci_low"] is not None
    assert s["converted_ci_low"] < s["converted_hit_rate"] < s["converted_ci_high"]


def test_senza_esiti_giudicati_non_c_e_un_intervallo() -> None:
    """`if rate is not None and eff_n` -> `or`: col mutante basta uno dei due,
    quindi `sized_interval(rate_pct=None, ...)` riceve un tasso inesistente.
    Un intervallo attorno a niente."""
    s = ss._return_summary([_esito(date(2026, 1, 1), colpo=None)])
    assert s["converted_hit_rate"] is None
    assert s["converted_ci_low"] is None
    assert s["converted_ci_high"] is None
    assert s["converted_effective_n"] == 0
