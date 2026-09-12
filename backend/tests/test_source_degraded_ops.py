"""Ogni `op` che il frontend chiede deve esistere nel catalogo.

⚠️ Il rischio e' scritto da mesi nel docstring di `source_catalog.known_ops()`
e finora NIENTE lo controllava:

    «Serve a rifiutare un `op` sconosciuto invece di rendere una lista vuota:
    vuota e indistinguibile da "tutto sano", quindi un refuso nel frontend
    renderebbe una scheda muta per sempre e nessuno lo vedrebbe mai.»

L'endpoint fa la sua parte — un `op` ignoto torna 422 — ma `SourceDegradedNote`
ha `retry: false` e non mostra nulla in caso di errore, deliberatamente (una
riga che compare perche' non si e' riusciti a sapere se c'e' un problema e' un
falso allarme). Le due scelte sono giuste separatamente e insieme producono il
silenzio: `op="fundamentls"` non rompe niente, non logga niente, e semplicemente
non avvisa mai.

⚠️ Il test vive nel BACKEND e legge i sorgenti del frontend, non il contrario.
`known_ops()` e' il proprietario unico dell'elenco; duplicarlo in TypeScript per
poterlo controllare da li' creerebbe la seconda copia che il controllo esiste
per impedire.
"""

import re
from pathlib import Path

import pytest

from app.services.source_catalog import known_ops

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"

#: `<SourceDegradedNote op="..."` su una o piu' righe.
_USO = re.compile(r'<SourceDegradedNote\b[^>]*?\bop="([a-z_]+)"', re.S)

#: Sotto questo numero il censimento non sta guardando l'app: un glob che
#: smette di risolvere renderebbe «ogni op e' valido» vero di un insieme vuoto,
#: che e' la forma registrata piu' volte in CLAUDE.md.
MINIMO_USI = 2


def _usi() -> list[tuple[str, str]]:
    """(file, op) per ogni montaggio della nota nel frontend."""
    out: list[tuple[str, str]] = []
    for f in FRONTEND.rglob("*.tsx"):
        if ".test." in f.name:
            continue
        testo = f.read_text(encoding="utf-8")
        for m in _USO.finditer(testo):
            out.append((f.name, m.group(1)))
    return out


def test_il_censimento_trova_i_montaggi():
    """Il pavimento, prima di ogni altra asserzione."""
    usi = _usi()
    assert len(usi) >= MINIMO_USI, (
        f"trovati solo {len(usi)} montaggi di SourceDegradedNote: o il "
        f"percorso {FRONTEND} non risolve, o qualcuno li ha rimossi. In "
        "entrambi i casi l'asserzione sotto sarebbe vera di niente."
    )


def test_ogni_op_richiesto_esiste_nel_catalogo():
    """Un refuso qui e' una scheda muta per sempre, senza errori da nessuna parte."""
    validi = known_ops()
    ignoti = sorted({(f, op) for f, op in _usi() if op not in validi})
    assert not ignoti, (
        f"op sconosciuti: {ignoti}. Quelli validi sono {sorted(validi)}. "
        "L'endpoint risponderebbe 422 e la nota, che non ritenta e non avvisa "
        "in caso di errore, resterebbe muta senza che nessuno se ne accorga."
    )


@pytest.mark.parametrize("op", ["news", "fundamentals"])
def test_gli_op_cablati_oggi_restano_validi(op):
    """Pin esplicito sui due montati.

    ⚠️ Non e' ridondante rispetto al test sopra: quello controlla cio' che
    TROVA, questo controlla che continuino a esistere DUE nomi specifici nel
    catalogo. Se un giorno `fundamentals` venisse rinominato lato backend, il
    test sopra passerebbe (il frontend verrebbe aggiornato nello stesso commit
    o no) mentre questo dice subito che il contratto e' cambiato.
    """
    assert op in known_ops()


def test_live_quote_NON_e_cablato_ed_e_una_scelta():
    """⚠️ L'omissione e' deliberata e va protetta dal prossimo «completamento».

    Il backlog prometteva questa nota su `fundamentals` E `live_quote`, «due
    righe per scheda, nessuna decisione nuova». La decisione c'era: `StockHeader`
    e `MarketStateBadge` mostrano GIA' `market_state === "STALE"`, cioe' lo
    stesso significato sulla stessa schermata. Due meccanismi per una cosa sola
    e' il difetto delle due tavolozze in un'altra forma — e qui i due possono
    anche CONTRADDIRSI, perche' `STALE` e' per-quotazione e vivo mentre la nota
    e' per-fonte e cachata due minuti.

    Se un giorno lo stato per-quotazione sparisse, questo test va cancellato
    insieme a quello — non aggirato.
    """
    montati = {op for _, op in _usi()}
    assert "live_quote" not in montati, (
        "live_quote e' stato cablato: verificare prima che StockHeader non "
        "mostri piu' market_state === 'STALE', altrimenti la stessa schermata "
        "porta due meccanismi per lo stesso significato."
    )
    # E il controllo che rende falsificabile l'asserzione sopra: lo stato
    # per-quotazione DEVE esistere davvero, o l'omissione non e' giustificata.
    header = (FRONTEND / "components" / "stock" / "StockHeader.tsx").read_text(encoding="utf-8")
    assert '"STALE"' in header, (
        "StockHeader non mostra piu' market_state STALE: la ragione per cui "
        "live_quote non ha la nota e' venuta meno, e la nota va aggiunta."
    )
