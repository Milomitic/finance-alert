"""Il generatore di mutanti e' logica pura, e va verificato come tale.

⚠️ Lo strumento che misura la qualita' dei test non puo' essere l'unica cosa
non misurata. Qui si verifica la META' PURA — l'analisi dell'AST — mentre la
meta' che lancia pytest e legge `git status` resta scoperta di proposito: un
test su quella verificherebbe `subprocess`, non questo modulo, e vive nella
linea di base del codice morto con la ragione scritta.
"""

import ast

from app.scripts.mutation_probe import EQUIVALENTI, genera


def _scrivi(tmp_path, sorgente: str):
    p = tmp_path / "bersaglio.py"
    p.write_text(sorgente, encoding="utf-8")
    return p


def test_scambia_i_confronti(tmp_path):
    """Il fuori-di-uno e' il difetto che questo strumento esiste per trovare."""
    p = _scrivi(tmp_path, "def f(x):\n    return x > 7\n")
    mutanti = genera(p)
    # Due mutanti e non uno: `x > 7` contiene sia un confronto sia una
    # costante, e ciascuna ne genera uno. Il conteggio sta scritto perche' la
    # prima stesura di questo test ne aspettava uno solo — le attese sbagliate
    # sono meta' del valore di scrivere un test.
    assert {(m.prima, m.dopo) for m in mutanti} == {("Gt", "GtE"), ("7", "8")}

    confronto = next(m for m in mutanti if m.prima == "Gt")
    # Il sorgente prodotto deve essere Python valido, o il mutante "muore" per
    # SyntaxError e conterebbe come ucciso senza aver provato nulla.
    assert "x >= 7" in confronto.sorgente
    ast.parse(confronto.sorgente)


def test_scambia_gli_operatori_booleani(tmp_path):
    p = _scrivi(tmp_path, "def f(a, b):\n    return a and b\n")
    mutanti = genera(p)
    assert [(m.prima, m.dopo) for m in mutanti] == [("And", "Or")]
    assert "a or b" in mutanti[0].sorgente


def test_incrementa_gli_interi_e_nega_i_booleani(tmp_path):
    p = _scrivi(tmp_path, "SOGLIA = 7\nATTIVO = True\n")
    mutanti = genera(p)
    assert {(m.prima, m.dopo) for m in mutanti} == {("7", "8"), ("True", "False")}


def test_NON_muta_le_stringhe(tmp_path):
    """⚠️ Deliberato: mutare una stringa produce quasi sempre un mutante banale
    — un messaggio di log diverso — che nessun test deve notare. I banali sono
    il rumore che fa spegnere questi strumenti, quindi non si generano."""
    p = _scrivi(tmp_path, 'def f():\n    return "ciao"\n')
    assert genera(p) == []


def test_un_mutante_per_volta(tmp_path):
    """Due mutazioni insieme possono annullarsi a vicenda, e allora un test che
    non se ne accorge non dice niente su nessuna delle due."""
    p = _scrivi(tmp_path, "def f(x, y):\n    return x > 1 and y < 2\n")
    mutanti = genera(p)
    # Cinque: Gt, And, Lt, 1->2, 2->3.
    assert len(mutanti) == 5
    for m in mutanti:
        diverse = sum(
            1 for a, b in zip(
                ["def", "f(x,", "y):", "return", "x", ">", "1", "and", "y", "<", "2"], m.sorgente.split(),
                strict=False,
            ) if a != b
        )
        assert diverse <= 2, f"mutante multiplo: {m.dopo}"


def test_ogni_equivalente_dichiarato_porta_una_RAGIONE():
    """⚠️ Un sopravvissuto senza spiegazione e' indistinguibile da un difetto.

    Questa lista e' anche il punto dove sarebbe piu' comodo nascondere un
    mutante scomodo, quindi la ragione non e' facoltativa."""
    assert EQUIVALENTI, "la lista non puo' essere vuota senza che nessuno lo noti"
    for chiave, ragione in EQUIVALENTI.items():
        assert len(ragione) > 60, f"{chiave}: ragione troppo breve per essere una ragione"
