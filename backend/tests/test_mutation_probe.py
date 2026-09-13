"""Il generatore di mutanti e' logica pura, e va verificato come tale.

⚠️ Lo strumento che misura la qualita' dei test non puo' essere l'unica cosa
non misurata. Qui si verifica la META' PURA — l'analisi dell'AST — mentre la
meta' che lancia pytest e legge `git status` resta scoperta di proposito: un
test su quella verificherebbe `subprocess`, non questo modulo, e vive nella
linea di base del codice morto con la ragione scritta.
"""

import ast
from pathlib import Path

import pytest

from app.scripts import mutation_probe
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


# ─── La linea di base si LEGGE, e leggerla male costa piu' che non leggerla ──
#
# ⚠️ `_carica_conteggi` e' stata trovata mai eseguita dal cancello del codice
# morto. Non e' un dettaglio di copertura: e' la funzione che rende il
# cricchetto PER MODULO, ed era gia' la sede di un difetto reale — una passata
# ristretta a un modulo confrontata contro la linea di base INTERA aveva
# riportato «76 mutanti uccisi» dove la verita' era 17.
#
# Il rischio che resta e' il suo ramo di errore. Torna `{}` su file assente o
# illeggibile, il che e' giusto per LEGGERE (non si sa nulla) ed e' distruttivo
# in SCRITTURA: `main --scrivi` fonde i conteggi noti con quelli appena
# misurati, quindi con `{}` i moduli non toccati in quella passata sparirebbero
# dal file in silenzio. Il cricchetto tornerebbe verde per sottrazione.


def test_i_conteggi_per_modulo_si_leggono_dal_file_vero():
    """Il pavimento: senza, ogni asserzione sotto e' vera di un file vuoto."""
    conteggi = mutation_probe._carica_conteggi()
    assert len(conteggi) >= 4, f"solo {len(conteggi)} moduli nella linea di base"
    for modulo, c in conteggi.items():
        assert modulo.endswith(".py"), modulo
        assert set(c) == {"mutanti", "uccisi"}, c
        assert 0 <= c["uccisi"] <= c["mutanti"], f"{modulo}: {c}"


def test_conteggi_e_lista_non_si_contraddicono():
    """⚠️ Le due meta' del file contano cose DIVERSE, e serve saperlo.

    `mutanti - uccisi` e' il numero esatto di mutanti sopravvissuti. La lista
    `sopravvissuti` e' piu' CORTA di due scarti, entrambi voluti:

      - gli EQUIVALENTI dichiarati non ci entrano (sopravvivono, ma con una
        ragione scritta accanto);
      - la chiave «file:riga  prima -> dopo» NON e' unica — due mutazioni
        identiche sulla stessa riga la condividono — e il file conserva un
        insieme, quindi i doppioni collassano. Il commento accanto alla
        scrittura lo dichiara.

    Quindi l'uguaglianza NON vale e pretenderla renderebbe questo test rosso su
    un file corretto (misurato: 63 in lista contro 70 attesi, differenza = 2
    equivalenti + 5 doppioni). Vale la DISUGUAGLIANZA, che e' comunque la
    direzione in cui sta il difetto reale: una lista piu' lunga del conteggio
    significa voci che nessuna passata ha misurato — per esempio una passata
    ristretta che ha riscritto i conteggi di un modulo lasciando in piedi i
    sopravvissuti di un altro.
    """
    conteggi = mutation_probe._carica_conteggi()
    vivi = mutation_probe._carica_base()
    assert vivi, "nessun sopravvissuto: il file non e' stato letto"
    for modulo, c in conteggi.items():
        in_lista = sum(1 for s in vivi if s.startswith(modulo))
        equivalenti = sum(1 for s in EQUIVALENTI if s.startswith(modulo))
        assert in_lista + equivalenti <= c["mutanti"] - c["uccisi"], (
            f"{modulo}: lista {in_lista} + equivalenti {equivalenti} superano "
            f"i {c['mutanti'] - c['uccisi']} sopravvissuti misurati. Il file "
            "porta voci che nessuna passata ha prodotto."
        )


def test_ogni_modulo_contato_ha_dei_mutanti():
    """Un modulo con zero mutanti generati non e' «pulito»: e' non misurato, e
    contarlo come misurato gonfia il denominatore a schermo."""
    for modulo, c in mutation_probe._carica_conteggi().items():
        assert c["mutanti"] > 0, f"{modulo} e' in linea di base con zero mutanti"


@pytest.mark.parametrize("contenuto", [None, "{non json", '{"per_modulo": 3}'])
def test_un_file_illeggibile_da_vuoto_e_non_esplode(tmp_path, monkeypatch, contenuto):
    """⚠️ Vuoto e' la risposta giusta in lettura, ed e' una TRAPPOLA in
    scrittura: `--scrivi` fonde il noto col misurato, quindi partendo da vuoto
    cancellerebbe i moduli non toccati dalla passata. Il commento accanto a
    `--scrivi` lo dice; questo test fissa la meta' che si puo' verificare."""
    finto = tmp_path / "mutation_baseline.json"
    if contenuto is not None:
        finto.write_text(contenuto, encoding="utf-8")
    monkeypatch.setattr(mutation_probe, "LINEA_BASE", finto)
    assert mutation_probe._carica_conteggi() == {}
    assert mutation_probe._carica_base() == set()


# ─── La chiave di linea di base non deve dipendere dalle righe ────────────


_SORGENTE = '''def f(x, y):
    if x > 0 and y > 0:
        return x >= 10
    return False


class C:
    def m(self, z):
        return z < 5
'''


def _chiavi(tmp_path, testo, nome="m.py"):
    p = tmp_path / nome
    p.write_text(testo, encoding="utf-8")
    return {mutation_probe.chiave("m.py", x) for x in mutation_probe.genera(p)}


def _chiavi_vecchia_forma(tmp_path, testo, nome="v.py"):
    """La forma che c'era prima: `file:riga  prima -> dopo`."""
    p = tmp_path / nome
    p.write_text(testo, encoding="utf-8")
    return {f"m.py:{x.riga}  {x.prima} -> {x.dopo}" for x in mutation_probe.genera(p)}


def test_un_COMMENTO_non_sposta_nessuna_chiave(tmp_path):
    """⚠️ Il difetto che questa chiave esiste per chiudere.

    `mutation_probe` gira in `nightly.yml` senza `continue-on-error` e rende 1
    quando trova sopravvissuti nuovi. Con la chiave `file:riga`, aggiungere due
    righe di commento in cima a un modulo sorvegliato spostava OGNI voce sotto
    di esso: la notturna diventava rossa su codice che nessuno aveva toccato,
    che e' la forma che CLAUDE.md registra tre volte come fatale a un cancello.

    Misurato quando e' successo davvero: nove righe di commento in
    `signal_outcome_service` -> quattro falsi sopravvissuti."""
    assert _chiavi(tmp_path, _SORGENTE) == _chiavi(
        tmp_path, "# una riga\n# e un'altra\n\n" + _SORGENTE, nome="b.py"
    )


def test_controllo_negativo_la_VECCHIA_forma_si_spostava(tmp_path):
    """Senza questo, il test sopra sarebbe vero anche di una chiave che non ha
    risolto niente — per esempio se `genera` rendesse una lista vuota."""
    prima = _chiavi_vecchia_forma(tmp_path, _SORGENTE)
    dopo = _chiavi_vecchia_forma(tmp_path, "# una riga\n# e un'altra\n\n" + _SORGENTE,
                                 nome="v2.py")
    assert prima, "nessun mutante generato: il confronto sarebbe vuoto"
    assert prima != dopo, "la vecchia chiave non si spostava: il test e' cieco"


def test_l_ambito_e_la_funzione_PIU_INTERNA(tmp_path):
    """Il metodo dentro la classe deve leggere `C.m`, non `C` e non `<modulo>`:
    altrimenti due funzioni della stessa classe condividerebbero le chiavi."""
    p = tmp_path / "a.py"
    p.write_text(_SORGENTE, encoding="utf-8")
    ambiti = {x.ambito for x in mutation_probe.genera(p)}
    assert "C.m" in ambiti
    assert "f" in ambiti


def test_due_mutazioni_IDENTICHE_nello_stesso_ambito_restano_distinte(tmp_path):
    """L'ordinale `#N` conserva la risoluzione che la vecchia chiave perdeva
    quando due mutazioni identiche cadevano sulla stessa riga: se una viene
    uccisa e l'altra no, devono restare due voci."""
    p = tmp_path / "d.py"
    p.write_text("def g(a, b):\n    return (a > 0) and (b > 0)\n", encoding="utf-8")
    mutanti = mutation_probe.genera(p)
    zeri = [m for m in mutanti if (m.prima, m.dopo) == ("0", "1")]
    assert len(zeri) == 2, f"attesi due `0 -> 1`, trovati {len(zeri)}"
    assert len({mutation_probe.chiave("d.py", m) for m in zeri}) == 2


def test_ogni_chiave_in_linea_di_base_ha_la_forma_NUOVA():
    """Il pavimento: una voce nella vecchia forma sopravvivrebbe in silenzio al
    confronto (non corrisponde a nessun mutante, quindi non viene mai ne'
    uccisa ne' segnalata) e resterebbe li' per sempre a gonfiare l'arretrato."""
    vivi = mutation_probe._carica_base()
    assert vivi, "linea di base vuota: l'asserzione sarebbe vera di niente"
    for s in vivi:
        assert "::" in s and "#" in s, f"chiave nella vecchia forma: {s}"


def test_ogni_EQUIVALENTE_ha_la_forma_NUOVA():
    """Stessa ragione, e qui il costo e' peggiore: un equivalente con la chiave
    sbagliata non protegge piu' niente, e il mutante che dichiarava ricompare
    come sopravvissuto nuovo — cioe' il cancello arrossisce su una cosa gia'
    decisa."""
    for s in EQUIVALENTI:
        assert "::" in s and "#" in s, f"chiave nella vecchia forma: {s}"


def test_ogni_EQUIVALENTE_corrisponde_a_un_mutante_che_ESISTE():
    """⚠️ Una chiave dichiarata che non corrisponde a nessun mutante non
    protegge niente, e il modo in cui fallisce e' silenzioso: il mutante che
    diceva di coprire ricompare come «sopravvissuto nuovo» e il cancello
    arrossisce su una cosa gia' decisa, mentre la voce resta nel file a
    sembrare una spiegazione.

    Succede ogni volta che qualcuno modifica la funzione che contiene il
    mutante — ed e' esattamente il caso in cui la decisione andava rivista, non
    ereditata. Genera i mutanti di tutti i moduli bersaglio: due secondi, senza
    eseguire un solo test."""
    reali = set()
    for modulo in mutation_probe.BERSAGLI:
        for m in mutation_probe.genera(Path(modulo)):
            reali.add(mutation_probe.chiave(modulo, m))
    assert reali, "nessun mutante generato: l'asserzione sarebbe vera di niente"
    orfane = sorted(k for k in EQUIVALENTI if k not in reali)
    assert not orfane, (
        "queste voci di EQUIVALENTI non corrispondono a nessun mutante e non "
        f"proteggono piu' niente: {orfane}"
    )
