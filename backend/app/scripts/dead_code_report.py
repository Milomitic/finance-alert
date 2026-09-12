"""Quali funzioni di `app/` non vengono eseguite da NESSUN test.

⚠️ Nasce da un difetto costoso e ricorrente: codice corretto, documentato,
creduto attivo, e mai eseguito.

`_RANGE_PERIODS` in `stock_detail_service` conteneva una tabella di periodi per
timeframe. La sua unica consumatrice, `_compute_indicator_series`, aveva ZERO
chiamanti in tutto il repository — ma CLAUDE.md documentava quella tabella come
il comportamento reale dell'app, e chiunque andasse a controllare la trovava e
ci credeva. Il codice morto non sta fermo: **avvalora la documentazione stale**,
ed e' cosi' che un'istruzione sbagliata sopravvive a una verifica.
Stessa forma per i due `except UpstreamError` che non potevano scattare, perche'
il servizio sotto non solleva quel tipo.

⚠️ NON e' una percentuale di copertura. Una percentuale misura quante righe
sono state toccate e si Goodhart-izza al primo tentativo di alzarla; questo
chiede una cosa sola e verificabile: «questa funzione e' mai partita?».

⚠️ LA COPERTURA DIPENDE DALL'AMBIENTE, e la linea di base e' quella di CI.
Sei funzioni risultavano vive su Windows e morte in CI al primo giro:
`spa_fallback` perche' senza `frontend/dist` il fallback SPA non viene montato,
le altre perche' una configurazione locale accendeva rami che in CI restano
spenti. Rigenerare la linea di base in locale produce un file piu' STRETTO, che
fa arrossare la CI su codice che nessuno ha toccato. Rigenerarla quindi dai
risultati di CI, o accettare che in locale alcune voci appaiano come «ora
coperte» — e' una nota, non un errore.

La risposta interessante non e' il numero, e' il DELTA. L'arretrato esiste e in
buona parte e' legittimo (script one-off, rami difensivi, percorsi che toccano
la rete). Quello che non deve succedere e' che ne nasca uno nuovo senza che
nessuno lo noti — quindi si congela una linea di base e si sorveglia la crescita.

    cd backend
    uv run coverage run -m pytest tests/ -q
    uv run coverage json -o .coverage.json
    uv run python -m app.scripts.dead_code_report            # confronta
    uv run python -m app.scripts.dead_code_report --scrivi   # rigenera
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
COVERAGE_JSON = RADICE / ".coverage.json"
LINEA_BASE = RADICE / "app" / "data" / "dead_code_baseline.json"

#: Sotto questo numero di funzioni censite, la misura non sta guardando l'app:
#: un `coverage.json` parziale o un percorso sbagliato darebbero un insieme
#: quasi vuoto, e «nessuna funzione morta nuova» sarebbe vero di niente.
MINIMO_FUNZIONI = 800


@dataclass(frozen=True)
class Funzione:
    file: str
    nome: str
    riga: int

    @property
    def chiave(self) -> str:
        return f"{self.file}::{self.nome}"


def _funzioni_del_modulo(sorgente: str, percorso: str) -> list[tuple[Funzione, set[int]]]:
    """Ogni funzione del file con l'insieme delle righe del suo CORPO.

    Si usa il corpo e non l'intervallo completo perche' la riga del `def` e
    quelle dei decoratori vengono eseguite all'IMPORT: contarle farebbe
    sembrare viva qualunque funzione mai chiamata, che e' esattamente
    l'illusione da evitare.
    """
    try:
        albero = ast.parse(sorgente)
    except SyntaxError:
        return []
    out: list[tuple[Funzione, set[int]]] = []
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        righe: set[int] = set()
        for figlio in nodo.body:
            for sotto in ast.walk(figlio):
                if hasattr(sotto, "lineno"):
                    righe.add(sotto.lineno)
        if not righe:
            continue
        qualificato = nodo.name
        out.append((Funzione(percorso, qualificato, nodo.lineno), righe))
    return out


def morte(coverage_json: Path = COVERAGE_JSON) -> tuple[list[Funzione], int]:
    """Funzioni con zero righe di corpo eseguite, piu' il totale censito."""
    dati = json.loads(coverage_json.read_text(encoding="utf-8"))
    fuori: list[Funzione] = []
    totale = 0
    for percorso, info in sorted(dati.get("files", {}).items()):
        norm = percorso.replace("\\", "/")
        if "/app/" not in f"/{norm}" and not norm.startswith("app/"):
            continue
        f = RADICE / percorso
        if not f.exists():
            continue
        eseguite = set(info.get("executed_lines", []))
        for fn, righe in _funzioni_del_modulo(f.read_text(encoding="utf-8"), norm):
            totale += 1
            if not (righe & eseguite):
                fuori.append(fn)
    return fuori, totale


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scrivi", action="store_true",
                    help="rigenera la linea di base invece di confrontarla")
    ap.add_argument("--coverage", type=Path, default=COVERAGE_JSON)
    args = ap.parse_args()

    if not args.coverage.exists():
        print(f"manca {args.coverage}: esegui prima "
              "`coverage run -m pytest tests/ -q && coverage json -o .coverage.json`",
              file=sys.stderr)
        return 2

    fuori, totale = morte(args.coverage)
    # ⚠️ Deduplicato: `file::nome` non e' unico — funzioni annidate e omonime
    # in scope diversi dello stesso modulo producono la stessa chiave. Senza
    # `set`, il conteggio stampato contava i duplicati mentre il confronto
    # usava un insieme, e i due numeri non tornavano (346 contro 345) per un
    # motivo che sembrava un difetto e non lo era.
    chiavi = sorted({f.chiave for f in fuori})

    if totale < MINIMO_FUNZIONI:
        print(f"censite solo {totale} funzioni (minimo {MINIMO_FUNZIONI}): il "
              "rapporto non sta guardando l'app intera, quindi il confronto "
              "sotto non significherebbe nulla.", file=sys.stderr)
        return 2

    if args.scrivi:
        LINEA_BASE.parent.mkdir(parents=True, exist_ok=True)
        LINEA_BASE.write_text(json.dumps({
            "_perche": (
                "Funzioni di app/ che nessun test esegue. Arretrato MISURATO, "
                "non obiettivo: molte sono legittime (script one-off, rami "
                "difensivi, percorsi di rete). Il gate impedisce che ne "
                "compaiano di NUOVE senza che qualcuno se ne accorga — perche' "
                "il codice morto avvalora la documentazione stale, come fece "
                "_RANGE_PERIODS. Rigenerare solo dopo aver cancellato o coperto "
                "qualcosa, mai per far passare la CI."
            ),
            "totale_funzioni": totale,
            "morte": chiavi,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"linea di base scritta: {len(chiavi)} morte su {totale} funzioni")
        return 0

    if not LINEA_BASE.exists():
        print(f"manca {LINEA_BASE}: generala con --scrivi", file=sys.stderr)
        return 2
    base = json.loads(LINEA_BASE.read_text(encoding="utf-8"))
    note = set(base.get("morte", []))
    nuove = sorted(set(chiavi) - note)
    risorte = sorted(note - set(chiavi))

    print(f"funzioni censite: {totale}")
    print(f"mai eseguite: {len(chiavi)} (linea di base: {len(note)})")
    if risorte:
        print(f"\n  ora coperte o rimosse ({len(risorte)}): "
              f"{', '.join(risorte[:8])}{' ...' if len(risorte) > 8 else ''}")
        print("  stringi la linea di base: --scrivi")
    if nuove:
        print(f"\nNUOVE funzioni mai eseguite ({len(nuove)}):", file=sys.stderr)
        for k in nuove:
            print(f"  {k}", file=sys.stderr)
        print("\nSe e' codice che serve, coprilo con un test. Se non serve, "
              "cancellalo: il codice morto avvalora la documentazione stale.",
              file=sys.stderr)
        return 1
    print("\nnessuna nuova funzione morta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
