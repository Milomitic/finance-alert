"""L'intervallo attorno a una MEDIA, che non e' quello attorno a un tasso.

Il cubo dei detector mette un intervallo di Wilson attorno a una percentuale,
ed e' giusto: una percentuale e' una proporzione binomiale. L'attesa in R e'
la media di una variabile CONTINUA e per lei Wilson non e' definito — servono
la deviazione standard del campione e una t di Student.

⚠️ Il punto e' lo stesso di `sized_interval`: la stima puntuale usa TUTTE le
righe, ma la LARGHEZZA e' pagata sul numero di osservazioni indipendenti.
Finestre di 21 sedute che si sovrappongono non sono estrazioni indipendenti,
e trattarle come tali e' cio' che teneva acceso un allarme su 1372 righe che
erano dodici finestre.
"""
from __future__ import annotations

import pytest

from app.stats.media import mean_interval, t_quantile

# Quantili al 97,5% della t di Student, da tavola.
_TAVOLA = {1: 12.7062, 2: 4.3027, 5: 2.5706, 10: 2.2281, 30: 2.0423, 100: 1.9840}


@pytest.mark.parametrize(("df", "atteso"), sorted(_TAVOLA.items()))
def test_il_quantile_combacia_con_la_tavola(df: int, atteso: float) -> None:
    """⚠️ Verificato contro numeri INDIPENDENTI, non contro se stesso.

    Un'implementazione numerica confrontata solo con la propria uscita e' vera
    per definizione. Questi valori vengono da una tavola della t, e sono
    l'unica cosa che distingue una formula giusta da una plausibile.
    """
    assert t_quantile(0.975, df) == pytest.approx(atteso, abs=5e-4)


def test_con_molti_gradi_di_liberta_la_t_tende_alla_normale() -> None:
    assert t_quantile(0.975, 5000) == pytest.approx(1.96, abs=2e-3)


def test_la_media_sta_al_centro_dell_intervallo() -> None:
    valori = [1.0, 2.0, 3.0, 4.0, 5.0]
    basso, alto = mean_interval(valori, effective_n=len(valori))
    assert (basso + alto) / 2 == pytest.approx(3.0)


def test_un_campione_senza_dispersione_da_un_intervallo_di_ampiezza_zero() -> None:
    basso, alto = mean_interval([2.0] * 6, effective_n=6)
    assert basso == pytest.approx(2.0)
    assert alto == pytest.approx(2.0)


def test_MENO_osservazioni_indipendenti_ALLARGANO_l_intervallo() -> None:
    """Il comportamento per cui questa funzione esiste.

    Le stesse venti righe valgono venti estrazioni o quattro a seconda di
    quanto le loro finestre si sovrappongono, e l'intervallo deve dirlo.
    """
    valori = [0.5, -1.0, 2.0, -1.0, 4.0, -1.0, 1.5, -1.0, 3.0, -1.0] * 2
    stretto = mean_interval(valori, effective_n=20)
    largo = mean_interval(valori, effective_n=4)
    assert (largo[1] - largo[0]) > (stretto[1] - stretto[0]) * 2


def test_sotto_due_osservazioni_indipendenti_NON_c_e_un_intervallo() -> None:
    """⚠️ None, non un intervallo enorme.

    Con una sola osservazione indipendente la dispersione non e' stimabile, e
    stampare un intervallo largo quanto si vuole suggerirebbe comunque che
    una misura ci sia. «Non concludente» e' la risposta vera.
    """
    assert mean_interval([1.0, 2.0, 3.0], effective_n=1) is None
    assert mean_interval([], effective_n=10) is None


def test_la_stima_puntuale_usa_TUTTE_le_righe_non_solo_le_indipendenti() -> None:
    """La media e' la migliore ipotesi disponibile e usa tutto il campione;
    solo la larghezza paga la sovrapposizione. Stessa convenzione di
    `sized_interval`, e cambiarla qui renderebbe i due riquadri incoerenti
    sullo stesso schermo."""
    valori = [0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 0.0, 10.0]
    basso, alto = mean_interval(valori, effective_n=2)
    assert (basso + alto) / 2 == pytest.approx(5.0)
