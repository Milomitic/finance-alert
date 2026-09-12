"""I test NOTEREBBERO un errore, o si limitano a eseguire la riga?

⚠️ E' la domanda che la copertura non fa. «Questa riga e' stata eseguita» e
«un suo errore verrebbe visto» sono cose diverse, e questo repo ha gia'
registrato quattro casi in cui coincidevano solo in apparenza: `toEqual` sui
nodi DOM (struttura al posto dell'identita'), il test sui giorni vero in UTC
cioe' in CI, la scheda filtri con tre aree chiuse, il `localStorage` di Node 25
che ingoiava ogni scrittura. In tutti e quattro il test passava, la riga era
coperta, e il difetto sarebbe passato.

Il modo sistematico di chiederlo e' rompere il codice apposta e guardare se
qualcuno protesta. Un mutante SOPRAVVISSUTO — codice alterato, suite ancora
verde — segnala una riga la cui correttezza nessuno sta verificando.

⚠️ PERCHE' UN MOTORE FATTO IN CASA E NON `mutmut`. mutmut e' lo strumento
standard ed e' stata la prima scelta: installato, configurato, e poi
`mutmut run` risponde «To run mutmut on Windows, please use the WSL». Avrei
potuto configurarlo solo per la CI, ma spedire un cancello che non ho MAI visto
girare e' esattamente il difetto che questo lavoro sta chiudendo — la stessa
forma dell'unit k3s e del livello apt. Questo motore ha meno operatori e in
cambio si esegue ovunque, si legge in una pagina, e non aggiunge dipendenze
(mutmut ne portava tre, fra cui una TUI).

⚠️ AMBITO RISTRETTO, e non per pigrizia. Mutare tutta `app/` significherebbe ore
per passata, e un cancello che nessuno aspetta viene spento. Si mutano i moduli
che questo repo ha deliberatamente consolidato in un PROPRIETARIO UNICO, cioe'
quelli dove un difetto si propaga a ogni schermata invece di restare locale.

    cd backend
    PYTHONPATH=. python -m app.scripts.mutation_probe            # tutti
    PYTHONPATH=. python -m app.scripts.mutation_probe --modulo fx_service
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]

#: modulo -> test che devono accorgersene.
#:
#: I test sono elencati esplicitamente e non dedotti: una passata che lancia
#: l'intera suite per ogni mutante costerebbe ore, e soprattutto non direbbe
#: QUALE test avrebbe dovuto proteggere quella riga.
BERSAGLI: dict[str, list[str]] = {
    # La provenienza dell'immagine: piccola, nuova, e il suo unico compito e'
    # distinguere tre stati (fresca / stantia / IGNOTA). Un fuori-di-uno sulla
    # soglia o un `None` collassato su `False` sono difetti silenziosi.
    "app/services/image_provenance.py": [
        "tests/test_image_provenance.py",
    ],
    # L'etichetta della valuta: proprietario unico dopo che la logica dei
    # penny era quintuplicata in cinque servizi.
    "app/services/currency_units.py": [
        "tests/test_currency_label.py",
        "tests/test_alert_currency.py",
        "tests/test_ohlcv_currency_gate.py",
    ],
    # La conversione in dollari: un errore qui ha gia' fatto passare 75 titoli
    # per mega-cap che non lo erano (vedi risk.py in CLAUDE.md).
    "app/services/fx_service.py": [
        "tests/test_fx_honesty.py",
        "tests/test_position_fx.py",
        "tests/test_risk_market_cap_currency.py",
    ],
    # Il tetto di 28 giorni sull'attesa di un setup: la scelta fra finestra
    # scorrevole e tetto e' stata misurata, e un fuori-di-uno la disfa.
    "app/services/setup_service.py": [
        "tests/test_setup_service.py",
    ],
}


#: Sopravvissuti EQUIVALENTI: il codice mutato fa davvero la stessa cosa, o la
#: differenza e' deliberatamente tollerata. Vanno elencati CON LA RAGIONE, non
#: nascosti — un sopravvissuto senza spiegazione e' indistinguibile da una
#: lacuna, e dopo qualche mese nessuno sa piu' quale dei due fosse.
#:
#: ⚠️ Non e' il posto dove mettere i sopravvissuti scomodi. Al primo giro su
#: `image_provenance` ne sono emersi quattro: DUE erano lacune vere — il bordo
#: esclusivo della soglia (`>` contro `>=`, il fuori-di-uno piu' comune che
#: esista) e il taglio a dieci caratteri di una data con orario — e sono state
#: chiuse con un test. Solo le altre due stanno qui.
EQUIVALENTI: dict[str, str] = {
    "app/services/image_provenance.py:47  7 -> 8":
        "STALE_AFTER_DAYS: il test sulla soglia asserisce un INTERVALLO "
        "ragionevole (3-14) e non il valore esatto, di proposito — il numero e' "
        "una taratura, non un contratto, e fissarlo renderebbe rosso ogni "
        "ripensamento legittimo. Otto giorni resta una soglia sensata.",
    "app/services/image_provenance.py:54  True -> False":
        "`@dataclass(frozen=True)`: l'immutabilita' non ha un consumatore che "
        "la eserciti. E' igiene, non comportamento; un test che prova a scrivere "
        "su un campo verificherebbe la libreria standard, non questo modulo.",
}


@dataclass(frozen=True)
class Mutante:
    riga: int
    prima: str
    dopo: str
    sorgente: str


#: Scambi di confronto: il fuori-di-uno e' il difetto piu' comune e il piu'
#: facile da non notare, perche' il test tipico usa valori lontani dal bordo.
_CONFRONTI = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}


class _Riscrittore(ast.NodeTransformer):
    def __init__(self, bersaglio: int) -> None:
        self.bersaglio = bersaglio
        self.visti = 0
        self.applicato: tuple[int, str, str] | None = None

    def _prendi(self, nodo, prima: str, dopo: str) -> bool:
        self.visti += 1
        if self.visti - 1 != self.bersaglio:
            return False
        self.applicato = (getattr(nodo, "lineno", 0), prima, dopo)
        return True

    def visit_Compare(self, nodo: ast.Compare):
        self.generic_visit(nodo)
        if len(nodo.ops) == 1 and type(nodo.ops[0]) in _CONFRONTI:
            nuovo = _CONFRONTI[type(nodo.ops[0])]
            if self._prendi(nodo, type(nodo.ops[0]).__name__, nuovo.__name__):
                nodo.ops = [nuovo()]
        return nodo

    def visit_BoolOp(self, nodo: ast.BoolOp):
        self.generic_visit(nodo)
        nuovo = ast.Or if isinstance(nodo.op, ast.And) else ast.And
        if self._prendi(nodo, type(nodo.op).__name__, nuovo.__name__):
            nodo.op = nuovo()
        return nodo

    def visit_Constant(self, nodo: ast.Constant):
        # Solo interi e booleani: mutare una stringa produce quasi sempre un
        # mutante banale (un messaggio di log diverso) che nessun test deve
        # notare, e i banali sono il rumore che fa spegnere questi strumenti.
        if isinstance(nodo.value, bool):
            if self._prendi(nodo, str(nodo.value), str(not nodo.value)):
                return ast.Constant(value=not nodo.value)
        elif isinstance(nodo.value, int):
            if self._prendi(nodo, str(nodo.value), str(nodo.value + 1)):
                return ast.Constant(value=nodo.value + 1)
        return nodo


def _quanti(sorgente: str) -> int:
    r = _Riscrittore(-1)
    r.visit(ast.parse(sorgente))
    return r.visti


def genera(percorso: Path) -> list[Mutante]:
    originale = percorso.read_text(encoding="utf-8")
    out: list[Mutante] = []
    for i in range(_quanti(originale)):
        albero = ast.parse(originale)
        r = _Riscrittore(i)
        nuovo = r.visit(albero)
        if r.applicato is None:
            continue
        ast.fix_missing_locations(nuovo)
        riga, prima, dopo = r.applicato
        out.append(Mutante(riga, prima, dopo, ast.unparse(nuovo)))
    return out


def _suite_verde(test: list[str]) -> bool:
    esito = subprocess.run(
        [sys.executable, "-m", "pytest", *test, "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
        cwd=RADICE, capture_output=True, text=True,
    )
    return esito.returncode == 0


def _albero_pulito(percorsi: list[str]) -> bool:
    esito = subprocess.run(
        ["git", "status", "--porcelain", "--", *percorsi],
        cwd=RADICE, capture_output=True, text=True,
    )
    return esito.returncode == 0 and not esito.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modulo", help="sottostringa per restringere i bersagli")
    args = ap.parse_args()

    bersagli = {
        m: t for m, t in BERSAGLI.items()
        if not args.modulo or args.modulo in m
    }
    if not bersagli:
        print("nessun bersaglio", file=sys.stderr)
        return 2

    # ⚠️ Precondizione non negoziabile: questo strumento SCRIVE nei file
    # sorgente e li ripristina. Se l'albero e' gia' sporco, un'interruzione
    # renderebbe impossibile distinguere le modifiche di qualcuno da un
    # ripristino mancato — e si finirebbe per buttare lavoro vero, che e' il
    # modo in cui `git checkout --` ha gia' distrutto due volte codice in
    # questo repo.
    if not _albero_pulito(list(bersagli)):
        print("I file bersaglio hanno modifiche non committate. Committa o "
              "metti da parte prima: questo strumento li riscrive.", file=sys.stderr)
        return 2

    sopravvissuti: list[str] = []
    totale = 0
    for modulo, test in bersagli.items():
        percorso = RADICE / modulo
        originale = percorso.read_text(encoding="utf-8")
        mutanti = genera(percorso)
        print(f"\n{modulo}: {len(mutanti)} mutanti, test {' '.join(test)}")

        # Controllo negativo obbligatorio: se la suite bersaglio e' gia' rossa,
        # OGNI mutante risulterebbe "ucciso" e il rapporto sarebbe un verde
        # che non significa niente.
        if not _suite_verde(test):
            print("  la suite bersaglio e' gia' rossa: salto", file=sys.stderr)
            continue

        try:
            for n, m in enumerate(mutanti, 1):
                percorso.write_text(m.sorgente, encoding="utf-8")
                vivo = _suite_verde(test)
                stato = "SOPRAVVISSUTO" if vivo else "ucciso"
                totale += 1
                if vivo:
                    sopravvissuti.append(f"{modulo}:{m.riga}  {m.prima} -> {m.dopo}")
                print(f"  [{n}/{len(mutanti)}] riga {m.riga}: {m.prima} -> {m.dopo}  {stato}")
        finally:
            # Sempre, anche su eccezione o interruzione.
            percorso.write_text(originale, encoding="utf-8")

    print(f"\n{'=' * 60}")
    uccisi = totale - len(sopravvissuti)
    noti = [s for s in sopravvissuti if s in EQUIVALENTI]
    nuovi = [s for s in sopravvissuti if s not in EQUIVALENTI]
    print(
        f"mutanti: {totale}, uccisi {uccisi}, sopravvissuti "
        f"{len(sopravvissuti)} (di cui {len(noti)} equivalenti dichiarati)"
    )
    if noti:
        print("\nequivalenti noti:")
        for s in noti:
            print(f"  {s}")

    if not _albero_pulito(list(bersagli)):
        print("\nATTENZIONE: un file non e' stato ripristinato. Controlla `git diff`.",
              file=sys.stderr)
        return 2

    if nuovi:
        print("\nSOPRAVVISSUTI NUOVI - righe la cui correttezza nessun test verifica:",
              file=sys.stderr)
        for s in nuovi:
            print(f"  {s}", file=sys.stderr)
        print(
            "\nOgnuno e' una lacuna o un equivalente, e la differenza va DECISA, "
            "non rimandata: se e' una lacuna si scrive il test, se e' equivalente "
            "si mette in EQUIVALENTI con la ragione. Un sopravvissuto senza "
            "spiegazione e' indistinguibile da un difetto.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
