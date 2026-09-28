"""I tipi del frontend, generati dallo schema OpenAPI dell'app (FA-111).

    cd backend && ./.venv/Scripts/python.exe -m app.scripts.genera_tipi_frontend

Scrive due file in `frontend/src/api/`:

- `schema.gen.ts`: un'interfaccia TypeScript per ogni modello Pydantic che
  l'API espone, con gli stessi nomi;
- `tipi.verifica.ts`: per ogni tipo scritto a mano che ha un modello del
  server, un controllo che fa fallire `tsc` se il tipo dichiara un campo che il
  server non manda.

⚠️ Perche' esiste. `frontend/src/api/types.ts` (~1.600 righe) e' scritto a mano
sui modelli del backend, e una copia a mano diverge in silenzio: FA-055 e'
nato esattamente cosi'. Al primo giro questo controllo ha trovato un caso
vivo: `series_stalled` e `series_last_bar`, calcolati dal servizio, dichiarati
dal frontend, e SCARTATI dall'API perche' `AlertOut` non li nominava.

Due presidi, e nessuno dei due installa niente con npm — una scrittura npm su
Windows puo' togliere il ramo Linux dal lockfile (CLAUDE.md):

- `tests/test_tipi_frontend.py` rigenera i due file in memoria e fallisce se
  quelli committati sono indietro;
- `tsc -b`, cioe' `npm run build` in CI, compila `tipi.verifica.ts`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

FRONTEND_SRC = Path(__file__).resolve().parents[3] / "frontend" / "src"
DESTINAZIONE = FRONTEND_SRC / "api" / "schema.gen.ts"
VERIFICA = FRONTEND_SRC / "api" / "tipi.verifica.ts"

#: Abbinamenti che il nome da solo non trova: tipo del frontend -> modello.
ABBINAMENTI: dict[str, str] = {
    "ScanStatusInfo": "ScanStatusOut",
}

#: Omonimi che NON sono lo stesso dato. Si saltano, con la ragione.
OMONIMI: dict[str, str] = {
    "ScanStatus": "nel frontend e' l'unione degli stati di una scansione; il "
                  "payload e' ScanStatusInfo",
}

#: Campi che il frontend dichiara e il server non manda DI PROPOSITO: li
#: scrive il client. Ognuno con la ragione, altrimenti questo diventa il posto
#: dove nascondere il prossimo FA-055.
CAMPI_DEL_CLIENT: dict[str, tuple[set[str], str]] = {
    "Mover": ({"vol_as_of"}, "lo scrive lib/liveMovers.ts unendo i movers dal vivo"),
    "VolumeSpike": ({"vol_as_of"}, "eredita da Mover"),
    "TopVolume": ({"vol_as_of"}, "eredita da Mover"),
}

INTESTAZIONE = """\
/* GENERATO — non modificare a mano.
 *
 * Tradotto dallo schema OpenAPI dell'app da
 *   backend/app/scripts/genera_tipi_frontend.py
 * e tenuto allineato da backend/tests/test_tipi_frontend.py, che fallisce se
 * questo file e' indietro rispetto ai modelli del server (FA-111).
 *
 * Niente `eslint-disable`: il file non viola nessuna regola, e una direttiva
 * che non sopprime niente e' un avviso del lint completo.
 */
"""

_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_EXPORT = re.compile(r"^export (?:interface|type) (\w+)", re.M)


def _nome(ref: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", ref.rsplit("/", 1)[-1])


def _chiave(k: str) -> str:
    return k if _IDENT.match(k) else json.dumps(k)


def _unione(parti: list[str]) -> str:
    visti: list[str] = []
    for p in parti:
        if p not in visti:
            visti.append(p)
    # `null` in fondo: `string | null` si legge meglio di `null | string`.
    visti.sort(key=lambda p: p == "null")
    return " | ".join(visti) if visti else "never"


def tipo(s: Any, rientro: str = "") -> str:
    """Il tipo TypeScript di uno schema JSON."""
    if s is True or s == {}:
        return "unknown"
    if not isinstance(s, dict):
        return "unknown"
    if "$ref" in s:
        return _nome(s["$ref"])
    if "const" in s:
        return json.dumps(s["const"], ensure_ascii=False)
    if "enum" in s:
        return _unione([json.dumps(v, ensure_ascii=False) for v in s["enum"]])
    for chiave in ("anyOf", "oneOf"):
        if chiave in s:
            return _unione([tipo(x, rientro) for x in s[chiave]])
    if "allOf" in s:
        parti = [tipo(x, rientro) for x in s["allOf"]]
        return parti[0] if len(parti) == 1 else " & ".join(f"({p})" for p in parti)
    t = s.get("type")
    if isinstance(t, list):
        return _unione([tipo({**s, "type": x}, rientro) for x in t])
    if t == "string":
        return "string"
    if t in ("integer", "number"):
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "null":
        return "null"
    if t == "array":
        if "prefixItems" in s:
            return "[" + ", ".join(tipo(x, rientro) for x in s["prefixItems"]) + "]"
        interno = tipo(s.get("items", {}), rientro)
        return f"({interno})[]" if " " in interno else f"{interno}[]"
    if t == "object" or "properties" in s or "additionalProperties" in s:
        if s.get("properties"):
            return _oggetto(s, rientro)
        extra = s.get("additionalProperties", True)
        return f"Record<string, {tipo(extra, rientro)}>"
    return "unknown"


def _oggetto(s: dict[str, Any], rientro: str) -> str:
    richiesti = set(s.get("required", []))
    dentro = rientro + "  "
    righe = ["{"]
    for k, v in s.get("properties", {}).items():
        opzionale = "" if k in richiesti else "?"
        righe.append(f"{dentro}{_chiave(k)}{opzionale}: {tipo(v, dentro)};")
    righe.append(f"{rientro}}}")
    return "\n".join(righe)


def genera(schema_openapi: dict[str, Any]) -> str:
    modelli = schema_openapi.get("components", {}).get("schemas", {})
    blocchi = [INTESTAZIONE]
    for nome in sorted(modelli):
        s = modelli[nome]
        ts = _nome(nome)
        if s.get("type") == "object" or "properties" in s:
            blocchi.append(f"export interface {ts} {_oggetto(s, '')}\n")
        else:
            blocchi.append(f"export type {ts} = {tipo(s)};\n")
    return "\n".join(blocchi)


def _tipi_del_frontend(radice: Path) -> dict[str, list[str]]:
    """modulo -> nomi esportati, per ogni .ts scritto a mano sotto `radice`."""
    out: dict[str, list[str]] = {}
    for f in sorted(radice.rglob("*.ts")):
        rel = f.relative_to(radice).as_posix()
        if rel.endswith((".test.ts", ".gen.ts", ".verifica.ts")) or rel.startswith("test/"):
            continue
        nomi = _EXPORT.findall(f.read_text(encoding="utf-8"))
        if nomi:
            out["@/" + rel[:-3]] = nomi
    return out


def genera_verifica(schema_openapi: dict[str, Any], radice: Path = FRONTEND_SRC) -> str:
    """Il file che fa fallire `tsc` quando un tipo del frontend dichiara un
    campo che il server non manda: la forma di FA-055."""
    generati = {_nome(n) for n in schema_openapi.get("components", {}).get("schemas", {})}
    moduli = _tipi_del_frontend(radice)
    controlli: list[tuple[str, str, str, set[str]]] = []
    for m, nomi in moduli.items():
        for n in nomi:
            if n in OMONIMI:
                continue
            modello = ABBINAMENTI.get(n) or next((c for c in (n + "Out", n) if c in generati), None)
            if modello is not None:
                controlli.append((m, n, modello, CAMPI_DEL_CLIENT.get(n, (set(), ""))[0]))

    usati = sorted({m for m, *_ in controlli})
    alias = {m: f"M{i}" for i, m in enumerate(usati)}
    righe = [
        "/* GENERATO da backend/app/scripts/genera_tipi_frontend.py — non modificare.",
        " *",
        " * Per ogni tipo scritto a mano che ha un modello del server, `tsc` pretende",
        " * che il tipo NON dichiari campi che il server non manda (FA-111). Le",
        " * eccezioni, ognuna con la sua ragione, stanno nello script. */",
        'import type * as S from "./schema.gen";',
    ]
    righe += [f'import type * as {alias[m]} from "{m}";' for m in usati]
    righe += [
        "",
        "type SoloNelFrontend<F, S> = Exclude<keyof F, keyof S>;",
        "type Nessuno<T extends never> = T;",
        "",
    ]
    for m, n, modello, del_client in controlli:
        controllo = f"SoloNelFrontend<{alias[m]}.{n}, S.{modello}>"
        if del_client:
            esclusi = " | ".join(f'"{c}"' for c in sorted(del_client))
            controllo = f"Exclude<{controllo}, {esclusi}>"
        righe.append(f"export type _{alias[m]}_{n} = Nessuno<{controllo}>;")
    return "\n".join(righe) + "\n"


def schema_dell_app() -> dict[str, Any]:
    from app.main import app

    return app.openapi()


def main() -> int:
    schema = schema_dell_app()
    testo = genera(schema)
    DESTINAZIONE.write_text(testo, encoding="utf-8", newline="\n")
    verifica = genera_verifica(schema)
    VERIFICA.write_text(verifica, encoding="utf-8", newline="\n")
    print(f"scritti {DESTINAZIONE.name} ({testo.count('export ')} tipi) "
          f"e {VERIFICA.name} ({verifica.count('export type _')} controlli)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
