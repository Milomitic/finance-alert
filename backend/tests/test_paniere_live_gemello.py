"""Il gemello del paniere live nel frontend combacia con l'originale (FA-106).

`frontend/src/lib/paniereLive.ts` elenca le voci di contesto del jumbotron —
tutto `LIVE_ASSET_DEFINITIONS` tranne le tre americane e il VIX — per
disegnarle PRIMA che arrivino le quotazioni. Senza, la riga nasceva vuota e
cresceva di ~245px dopo 1,7 s, spingendo giu' la pagina.

Un gemello invecchia in silenzio: se il backend aggiunge o toglie un simbolo,
la riga si disegna con le voci sbagliate e poi salta di nuovo quando arrivano
quelle vere. Questo test lo dice prima. Il file TypeScript si legge come testo,
come gli altri test di questa cartella leggono YAML e regole.
"""

import re
from pathlib import Path

from app.api.market import LIVE_ASSET_DEFINITIONS

GEMELLO = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "paniereLive.ts"

# Le voci che il jumbotron mostra altrove: le tre americane nei loro riquadri,
# il VIX nel suo. Stesso elenco di `USA` in MarketPulseJumbotron.
FUORI_DAL_CONTESTO = {"^GSPC", "^IXIC", "^DJI", "^VIX"}

_VOCE = re.compile(
    r'\{\s*symbol:\s*"(?P<symbol>[^"]+)",\s*category:\s*"(?P<category>[^"]+)",'
    r'\s*flag:\s*(?:"(?P<flag>[^"]+)"|null)\s*\}'
)


def _gemello() -> list[tuple[str, str, str | None]]:
    testo = GEMELLO.read_text(encoding="utf-8")
    return [(m["symbol"], m["category"], m["flag"]) for m in _VOCE.finditer(testo)]


def _originale() -> list[tuple[str, str, str | None]]:
    return [
        (simbolo, categoria, bandiera)
        for simbolo, _nome, categoria, bandiera, _futures in LIVE_ASSET_DEFINITIONS
        if simbolo not in FUORI_DAL_CONTESTO
    ]


def test_il_gemello_elenca_le_stesse_voci_nello_stesso_ordine() -> None:
    gemello = _gemello()
    # Il pavimento: una regex che non trova niente renderebbe il confronto
    # sotto vero di due liste vuote.
    assert len(gemello) >= 10, f"lette solo {len(gemello)} voci da {GEMELLO.name}"
    assert gemello == _originale(), (
        "il paniere live del backend e il suo gemello nel frontend divergono: "
        "aggiorna frontend/src/lib/paniereLive.ts"
    )


def test_il_confronto_vede_una_voce_mancante() -> None:
    """Controllo negativo: togliere una voce dall'originale deve rompere
    l'uguaglianza, altrimenti il test sopra non sorveglia niente."""
    assert _gemello() != _originale()[:-1]
