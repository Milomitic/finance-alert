"""Il titolo sta davvero scambiando? La guardia che precede ogni detector.

Un detector legge una serie di prezzi e ne cerca una FORMA. Su un titolo che
non scambia la serie c'e' lo stesso — il fornitore riporta l'ultimo prezzo — e
una forma la si trova sempre: una linea piatta e' un supporto perfetto, e un
minimo mai rotto e' un ipervenduto che non rimbalza mai.

Due casi, misurati prima di scrivere la regola:

  - SOSPESO. BMPS.MI nel 2017: prezzo riportato fermo per mesi a volume zero.
    Il replay dello studio del 2026-09-23 l'ha visto emettere
    `oversold_reversal` e `trend_pullback` su quella linea, con ATR ~0 e quindi
    stop ~0: 162 righe su 453mila spostavano una media da −0,02 a −0,85 R.
  - BLOCCATO DA UN'OFFERTA. Un titolo sotto OPA scambia, ma al prezzo
    dell'offerta, e l'ATR crolla. Il 2026-09-23 la regola avrebbe fermato sei
    titoli e NESSUNO era sospeso: Iveco, Beazley, Intertek, Schroders, EA e
    Catalyst Pharma, tutti ancorati a un prezzo d'acquisto. Il motore aveva
    emesso 44 alert su quelle barre.

⚠️ Modulo FOGLIA senza dipendenze: la regola deve poterla importare chiunque
legga una serie, non solo lo scan. Una soglia che vive dentro un servizio con
mezzo stack dietro finisce riscritta a mano — questo repo l'ha gia' pagato coi
quattordici periodi degli indicatori.
"""
from __future__ import annotations

from collections.abc import Sequence

#: Sotto questa frazione del prezzo l'ATR non descrive un titolo che si muove.
#: Misurata sull'ultima barra dei 1.026 titoli del catalogo: il percentile 1
#: vale 0,62%, e sotto lo 0,3% stanno solo i sei ancorati a un'offerta.
ATR_MINIMO = 0.003

#: Quante barre di volume nullo fanno un titolo sospeso. Venti sedute sono un
#: mese: una seduta senza scambi capita (festivita' locali riempite dal
#: fornitore), un mese intero no.
BARRE_VOLUME = 20

VOLUME_NULLO = "volume_nullo"
PREZZO_FERMO = "prezzo_fermo"


def motivo_non_negoziato(
    *, atr: float | None, prezzo: float, volumi: Sequence[float],
) -> str | None:
    """Il motivo per cui su questa serie non si cercano segnali, o None.

    `volumi` e' la serie intera, di cui contano le ultime `BARRE_VOLUME`.
    ⚠️ Un volume MANCANTE (NaN) non e' un volume nullo: una fonte senza volumi
    non dice che il titolo e' fermo, dice che non lo sa, e la guardia non
    deve spegnere un titolo per un dato che non ha.
    """
    ultimi = [v for v in list(volumi)[-BARRE_VOLUME:] if v == v]
    if len(ultimi) >= BARRE_VOLUME and sum(ultimi) <= 0:
        return VOLUME_NULLO
    if atr is not None and atr == atr and prezzo > 0 and atr / prezzo < ATR_MINIMO:
        return PREZZO_FERMO
    return None
