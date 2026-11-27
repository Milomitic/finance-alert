"""Il calendario dei rendimenti: anni per mesi (FA-185, FA-195).

Proprietario unico del «rendimento di un mese»: da fine mese a fine mese,
cioe' dall'ultima chiusura del mese precedente all'ultima di questo. La
stagionalita' dello Studio e il calendario della pagina Mercati leggono questa
tabella, cosi' «aprile» vale lo stesso numero nelle due pagine.

Il mese in corso c'e', dichiarato parziale: e' il rendimento da fine mese
scorso all'ultima chiusura disponibile.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date


def fine_mese(date_: Sequence[date], chiusure: Sequence[float]) -> dict[tuple[int, int], float]:
    """(anno, mese) -> ultima chiusura positiva di quel mese."""
    out: dict[tuple[int, int], float] = {}
    for g, c in zip(date_, chiusure, strict=True):
        if c > 0:
            out[(g.year, g.month)] = c
    return out


def rendimenti_mensili(date_: Sequence[date], chiusure: Sequence[float]) -> dict[tuple[int, int], float]:
    """(anno, mese) -> rendimento da fine mese precedente a fine mese. Il
    primo mese della storia non ha un «prima» e non compare; un mese senza
    sedute fra due che ne hanno interrompe la catena (nessun rendimento
    inventato a cavallo del buco)."""
    fm = fine_mese(date_, chiusure)
    out: dict[tuple[int, int], float] = {}
    for (a, m), c in fm.items():
        prec = (a, m - 1) if m > 1 else (a - 1, 12)
        if prec in fm:
            out[(a, m)] = c / fm[prec] - 1.0
    return out


def calendario_mensile(date_: Sequence[date], chiusure: Sequence[float]) -> dict:
    """La tabella anni per mesi, dal piu' recente.

    {"anni": [{"anno", "mesi": [r | None] * 12, "anno_totale": r | None,
               "parziale": bool}],
     "media_mesi": [...12], "positivi_mesi": [...12], "casi_mesi": [...12],
     "ultimo_mese": "AAAA-MM"}

    `anno_totale` e' da fine anno precedente all'ultima chiusura dell'anno
    (non il prodotto dei mesi: uguale quando non ci sono buchi, onesto quando
    ci sono). `parziale` per l'anno in corso."""
    mensili = rendimenti_mensili(date_, chiusure)
    fm = fine_mese(date_, chiusure)
    if not mensili:
        return {"anni": [], "media_mesi": [None] * 12, "positivi_mesi": [None] * 12,
                "casi_mesi": [0] * 12, "ultimo_mese": None}
    anni = sorted({a for a, _ in mensili}, reverse=True)
    ultimo_anno = date_[-1].year
    righe = []
    for a in anni:
        mesi = [mensili.get((a, m)) for m in range(1, 13)]
        ultimo_dell_anno = max(((aa, mm) for (aa, mm) in fm if aa == a), default=None)
        inizio = fm.get((a - 1, 12))
        totale = None
        if ultimo_dell_anno is not None and inizio:
            fine_a = fm[ultimo_dell_anno]
            totale = fine_a / inizio - 1.0
        righe.append({"anno": a, "mesi": mesi, "anno_totale": totale, "parziale": a == ultimo_anno})
    per_mese: list[list[float]] = [[] for _ in range(12)]
    for (_a, m), r in mensili.items():
        per_mese[m - 1].append(r)
    media = [sum(v) / len(v) if v else None for v in per_mese]
    positivi = [sum(1 for x in v if x > 0) / len(v) if v else None for v in per_mese]
    ua, um = max(mensili)
    return {"anni": righe, "media_mesi": media, "positivi_mesi": positivi,
            "casi_mesi": [len(v) for v in per_mese], "ultimo_mese": f"{ua:04d}-{um:02d}"}
