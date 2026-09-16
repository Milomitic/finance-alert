"""Ogni test che importa un modulo sondato gira contro i suoi mutanti, o ha una ragione per non farlo.

`mutation_probe.BERSAGLI` dice quali file di test girano contro i mutanti di
ciascun modulo. Se un test che esercita il modulo manca dall'elenco, i mutanti
girano contro una suite che non lo contiene: la sonda riporta SOPRAVVISSUTI
NUOVI che sono falsi, e `nightly.yml` — che la esegue senza
`continue-on-error` — diventa rossa su codice che nessuno ha toccato.

⚠️ E' successo TRE volte il 2026-09-16, sempre per `setup_service`: i test di
FA-061/FA-071 (nove falsi sopravvissuti), `test_setup_base_rate.py` (tre falsi
su dieci «nuovi»), e `test_post_scan_perimetro.py`, trovato da questo stesso
file alla prima esecuzione. CLAUDE.md registrava gia' la lezione («un elenco di test
troppo CORTO in BERSAGLI produce falsi sopravvissuti»); niente la faceva
rispettare.

COME SI LEGGE UN IMPORT. La sorgente si analizza con `ast`, senza importare i
test. Non con un'espressione regolare, per due ragioni misurate a mano:
`from app.services import (a,\\n setup_service)` va su piu' righe, e
`from app.services import setup_base_rate` NON importa `setup_service` —
un confronto per prefisso lo conterebbe.

Cosa NON e' un import, deliberatamente: un riferimento solo come STRINGA
(`patch("app.services.setup_service.x")`). Una sostituzione rimpiazza il codice
del modulo invece di eseguirlo, quindi non puo' ucciderne un mutante. Misurato
il 2026-09-16: zero file nel repo riferiscono un modulo sondato solo cosi'.

LIMITE DICHIARATO: un test che esercita il modulo solo attraverso un ALTRO
modulo (importa `scan_service`, che chiama `setup_service`) non viene visto.
Questo controllo chiude gli import diretti, che sono stati tutti e tre i casi.
"""
from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

from app.scripts.mutation_probe import BERSAGLI, ESCLUSI_DAI_BERSAGLI

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"


def nome_puntato(modulo: str) -> str:
    """`app/services/setup_service.py` -> `app.services.setup_service`."""
    return modulo.removesuffix(".py").replace("/", ".")


@cache
def _nomi_importati(sorgente: str) -> frozenset[str]:
    """Ogni nome puntato che la sorgente importa, in qualunque punto del file.

    `import a.b.c` da' `a.b.c`; `from a.b import c` da' `a.b` e `a.b.c`, perche'
    `c` puo' essere un modulo. `ast.walk` visita anche gli import dentro le
    funzioni, che nei test di questo repo sono comuni.

    In cache per sorgente: ogni file si analizza UNA volta, non una per modulo
    sondato — la prima versione ne faceva ~3.500 per test e il file impiegava
    dieci secondi."""
    nomi: set[str] = set()
    for nodo in ast.walk(ast.parse(sorgente)):
        if isinstance(nodo, ast.Import):
            nomi.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            nomi.add(nodo.module)
            nomi.update(f"{nodo.module}.{a.name}" for a in nodo.names)
    return frozenset(nomi)


def importa(sorgente: str, nome: str) -> bool:
    """Se la sorgente importa il modulo `nome`. Confronto ESATTO sul nome
    puntato: `app.services.setup_base_rate` non e' `app.services.setup_service`."""
    return nome in _nomi_importati(sorgente)


def coperto(file_test: str, voci: list[str]) -> bool:
    """Una voce che finisce con `/` e' una DIRECTORY, e pytest la riceve cosi':
    `tests/signals/` copre i 45 file sotto di lei. Senza questa regola i test
    di `detectors/base` risulterebbero tutti mancanti."""
    return any(file_test == v or (v.endswith("/") and file_test.startswith(v)) for v in voci)


@cache
def _sorgenti() -> dict[str, str]:
    return {
        p.relative_to(BACKEND).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(TESTS.rglob("*.py"))
    }


def importatori(nome: str, sorgenti: dict[str, str]) -> list[str]:
    return [f for f, src in sorgenti.items() if importa(src, nome)]


def mancanti(
    bersagli: dict[str, list[str]],
    esclusi: dict[str, dict[str, str]],
    sorgenti: dict[str, str],
) -> dict[str, list[str]]:
    """{modulo: file che lo importano e non stanno ne' nell'elenco ne' fra gli esclusi}."""
    out: dict[str, list[str]] = {}
    for modulo, voci in bersagli.items():
        fuori = [
            f for f in importatori(nome_puntato(modulo), sorgenti)
            if not coperto(f, voci) and f not in esclusi.get(modulo, {})
        ]
        if fuori:
            out[modulo] = fuori
    return out


# ── il cancello ─────────────────────────────────────────────────────────────

def test_ogni_test_che_importa_un_modulo_sondato_e_nel_suo_elenco() -> None:
    buchi = mancanti(BERSAGLI, ESCLUSI_DAI_BERSAGLI, _sorgenti())
    assert not buchi, (
        "Test che importano un modulo sondato ma non girano contro i suoi "
        "mutanti — la sonda riporterebbe falsi sopravvissuti nuovi:\n"
        + "\n".join(f"  {m}\n" + "\n".join(f"      {f}" for f in fs) for m, fs in buchi.items())
        + "\n\nAggiungili all'elenco del modulo in `app/scripts/mutation_probe.py` "
        "(`BERSAGLI`), oppure — solo se NON possono uccidere un suo mutante — "
        "a `ESCLUSI_DAI_BERSAGLI` con la ragione scritta."
    )


# ── il pavimento ────────────────────────────────────────────────────────────

def test_il_censimento_trova_davvero_dei_test_e_degli_import() -> None:
    """⚠️ Senza pavimento il cancello sopra e' vero di niente: un glob che non
    risolve, o un matcher che non riconosce piu' un import, rende «nessun
    buco» per sempre. Misurato il 2026-09-16: 297 file, 78 import su 12
    moduli."""
    sorgenti = _sorgenti()
    assert len(sorgenti) >= 250

    per_modulo = {m: importatori(nome_puntato(m), sorgenti) for m in BERSAGLI}
    assert sum(len(v) for v in per_modulo.values()) >= 60
    # Un modulo senza nessun importatore vuol dire che il matcher ha smesso di
    # vederlo (o che il modulo e' stato rinominato e l'elenco no).
    assert all(per_modulo.values()), [m for m, v in per_modulo.items() if not v]


# ── il controllo negativo ───────────────────────────────────────────────────

def test_il_cancello_SA_fallire_su_un_elenco_troppo_corto() -> None:
    """La forma esatta dell'incidente: l'elenco di `setup_service` senza
    `test_setup_base_rate.py`. Deve essere nominato, e da solo."""
    modulo = "app/services/setup_service.py"
    assert "tests/test_setup_base_rate.py" in BERSAGLI[modulo], "il caso di prova non vale piu'"
    corto = {modulo: [v for v in BERSAGLI[modulo] if v != "tests/test_setup_base_rate.py"]}

    assert mancanti(corto, ESCLUSI_DAI_BERSAGLI, _sorgenti()) == {
        modulo: ["tests/test_setup_base_rate.py"],
    }


def test_una_voce_DIRECTORY_e_cio_che_copre_i_test_dei_segnali() -> None:
    """Controllo negativo della regola sulle directory: togliere
    `tests/signals/` deve far mancare MOLTI file. Se ne mancassero zero, la
    copertura verrebbe da un matcher che non vede niente, non dalla voce."""
    modulo = "app/signals/detectors/base.py"
    assert "tests/signals/" in BERSAGLI[modulo]
    senza = {modulo: [v for v in BERSAGLI[modulo] if v != "tests/signals/"]}

    buchi = mancanti(senza, ESCLUSI_DAI_BERSAGLI, _sorgenti())[modulo]
    assert len(buchi) >= 10
    assert all(f.startswith("tests/signals/") for f in buchi)


def test_il_matcher_legge_gli_import_e_non_i_nomi_simili() -> None:
    n = "app.services.setup_service"
    assert importa("from app.services.setup_service import x", n)
    assert importa("from app.services import setup_service", n)
    assert importa("from app.services import (\n    a,\n    setup_service as s,\n)", n)
    assert importa("import app.services.setup_service as s", n)
    assert importa("def test_x():\n    from app.services.setup_service import y\n", n)
    # ⚠️ Il falso positivo che un confronto per prefisso produrrebbe.
    assert not importa("from app.services import setup_base_rate", n)
    assert not importa("from app.services.setup_service_extra import x", n)
    assert not importa("import app.services", n)
    # Deliberato: una sostituzione per stringa non esegue il modulo.
    assert not importa('patch("app.services.setup_service.run")', n)


# ── le esclusioni restano vere ──────────────────────────────────────────────

def esclusioni_non_valide(
    esclusi: dict[str, dict[str, str]],
    bersagli: dict[str, list[str]],
    sorgenti: dict[str, str],
) -> list[str]:
    """Una voce esclusa invecchia in silenzio, come un EQUIVALENTE orfano:
    - se il file non importa piu' il modulo, la voce non esclude niente e resta
      a sembrare una spiegazione;
    - se il file sta ANCHE nell'elenco, le due scelte si contraddicono;
    - una ragione di poche parole non e' una decisione."""
    problemi = []
    for modulo, voci in esclusi.items():
        if modulo not in bersagli:
            problemi.append(f"{modulo}: non e' un modulo sondato")
            continue
        for f, ragione in voci.items():
            if f not in sorgenti:
                problemi.append(f"{f}: il file non esiste")
            elif not importa(sorgenti[f], nome_puntato(modulo)):
                problemi.append(f"{f}: non importa piu' {modulo}, la voce e' orfana")
            if coperto(f, bersagli[modulo]):
                problemi.append(f"{f}: escluso e insieme nell'elenco di {modulo}")
            if len(ragione.strip()) < 40:
                problemi.append(f"{f}: la ragione non spiega niente")
    return problemi


def test_ogni_esclusione_e_ancora_una_decisione_valida() -> None:
    problemi = esclusioni_non_valide(ESCLUSI_DAI_BERSAGLI, BERSAGLI, _sorgenti())
    assert not problemi, "\n".join(problemi)


def test_il_controllo_delle_esclusioni_SA_fallire() -> None:
    """Senza, il test sopra sarebbe vero anche di un controllo che non guarda
    niente — e con un insieme di esclusioni vuoto lo sarebbe comunque."""
    modulo = "app/services/setup_service.py"
    finti = {
        modulo: {
            # importa `setup_service`, ma sta gia' nell'elenco
            "tests/test_setup_base_rate.py": "una ragione abbastanza lunga da passare la soglia",
            # esiste, ma non importa `setup_service`
            "tests/test_mutation_probe_bersagli_completi.py": "una ragione abbastanza lunga da passare la soglia",
            # non esiste
            "tests/test_che_non_esiste.py": "una ragione abbastanza lunga da passare la soglia",
        },
        "app/services/modulo_inventato.py": {"tests/x.py": "qualunque"},
    }
    problemi = "\n".join(esclusioni_non_valide(finti, BERSAGLI, _sorgenti()))
    assert "escluso e insieme nell'elenco" in problemi
    assert "la voce e' orfana" in problemi
    assert "il file non esiste" in problemi
    assert "non e' un modulo sondato" in problemi

    corta = {modulo: {"tests/test_seed_e2e_valutazione.py": "costante"}}
    assert "non spiega niente" in "\n".join(esclusioni_non_valide(corta, BERSAGLI, _sorgenti()))
