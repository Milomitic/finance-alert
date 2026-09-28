"""I tipi generati del frontend restano allineati al server (FA-111).

Se un modello Pydantic cambia — un campo nuovo, uno tolto, uno rinominato — il
file generato va rigenerato, e con lui il controllo che confronta i tipi
scritti a mano. Questo test lo pretende: senza, il generato invecchierebbe in
silenzio e `tsc` verificherebbe il frontend contro un server che non esiste
piu'.

Se fallisce:

    cd backend && ./.venv/Scripts/python.exe -m app.scripts.genera_tipi_frontend
"""
import pytest

from app.scripts import genera_tipi_frontend as g

COMANDO = "cd backend && ./.venv/Scripts/python.exe -m app.scripts.genera_tipi_frontend"


@pytest.fixture(scope="module")
def schema():
    return g.schema_dell_app()


def _su_disco(path) -> str:
    # Git su Windows puo' mettere CRLF nella copia di lavoro: si confronta il
    # contenuto, non i fine riga.
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_schema_gen_e_aggiornato(schema) -> None:
    assert g.genera(schema) == _su_disco(g.DESTINAZIONE), (
        f"frontend/src/api/schema.gen.ts e' indietro rispetto ai modelli: {COMANDO}"
    )


def test_la_verifica_e_aggiornata(schema) -> None:
    assert g.genera_verifica(schema) == _su_disco(g.VERIFICA), (
        f"frontend/src/api/tipi.verifica.ts e' indietro (un tipo nuovo nel "
        f"frontend o un modello nuovo nel server): {COMANDO}"
    )


def test_la_verifica_controlla_davvero(schema) -> None:
    """Il pavimento: un generatore che non abbina niente produrrebbe un file
    vuoto e un `tsc` verde per costruzione."""
    testo = g.genera_verifica(schema)
    assert testo.count("export type _") >= 120
    for tipo in ("Alert, S.AlertOut", "Position, S.PositionOut", "PlatformHealth, S.PlatformHealthOut"):
        assert tipo in testo, tipo


def test_le_eccezioni_nominano_tipi_che_esistono(schema) -> None:
    """Un'eccezione orfana non protegge niente e resta a sembrare una
    spiegazione (la regola degli EQUIVALENTI della sonda di mutazione)."""
    esportati = {n for nomi in g._tipi_del_frontend(g.FRONTEND_SRC).values() for n in nomi}
    for nome in [*g.CAMPI_DEL_CLIENT, *g.OMONIMI, *g.ABBINAMENTI]:
        assert nome in esportati, f"eccezione per {nome}, che il frontend non esporta piu'"
    generati = {g._nome(n) for n in schema["components"]["schemas"]}
    assert set(g.ABBINAMENTI.values()) <= generati


@pytest.mark.parametrize(
    ("schema_json", "atteso"),
    [
        ({"anyOf": [{"type": "string"}, {"type": "null"}]}, "string | null"),
        ({"type": "array", "items": {"$ref": "#/components/schemas/AlertOut"}}, "AlertOut[]"),
        ({"type": "array", "items": {"anyOf": [{"type": "integer"}, {"type": "null"}]}}, "(number | null)[]"),
        ({"type": "object", "additionalProperties": {"type": "number"}}, "Record<string, number>"),
        ({"enum": ["bull", "bear"]}, '"bull" | "bear"'),
        ({"const": "earnings"}, '"earnings"'),
        ({"type": "array", "prefixItems": [{"type": "string"}, {"type": "number"}]}, "[string, number]"),
        ({}, "unknown"),
    ],
)
def test_la_traduzione(schema_json, atteso) -> None:
    assert g.tipo(schema_json) == atteso


def test_main_scrive_i_due_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(g, "DESTINAZIONE", tmp_path / "schema.gen.ts")
    monkeypatch.setattr(g, "VERIFICA", tmp_path / "tipi.verifica.ts")
    assert g.main() == 0
    assert "export interface AlertOut" in (tmp_path / "schema.gen.ts").read_text(encoding="utf-8")
    assert "Nessuno<" in (tmp_path / "tipi.verifica.ts").read_text(encoding="utf-8")
