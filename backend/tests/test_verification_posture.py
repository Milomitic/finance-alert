"""Le linee di base della verifica sono LEGGIBILI, e non sono vuote.

⚠️ Sono i due arretrati che questa sessione ha reso misurabili — funzioni mai
eseguite e violazioni di accessibilita' — e vivono in `app/data/` perche' quella
cartella finisce nell'immagine: la scheda «Verifica» del cruscotto mostra gli
stessi numeri che i cancelli fanno rispettare, da un file solo.

Il test che conta e' quello sul VUOTO. Svuotare una linea di base e' il modo
piu' rapido di far passare la CI, e senza un pavimento nessuno se ne
accorgerebbe: le asserzioni «non e' cresciuto» resterebbero vere di un insieme
vuoto — la forma registrata quattro volte in CLAUDE.md.
"""

import json
from pathlib import Path

import pytest

DATI = Path(__file__).resolve().parents[1] / "app" / "data"


def _carica(nome: str) -> dict:
    p = DATI / nome
    assert p.exists(), (
        f"{nome} manca. Le due linee di base viaggiano nell'immagine perche' "
        "il cruscotto le legge: se una sparisce, la scheda Verifica mente."
    )
    return json.loads(p.read_text(encoding="utf-8"))


def test_codice_morto_e_misurato():
    d = _carica("dead_code_baseline.json")
    assert d["totale_funzioni"] > 800, "censimento troppo piccolo per essere l'app"
    assert len(d["morte"]) > 100, (
        "arretrato sospettosamente piccolo: o qualcuno ha svuotato il file, o "
        "il rapporto girava su una copertura parziale."
    )
    # Assente non e' zero: se un giorno arrivasse davvero a zero, va celebrato
    # cambiando QUESTO test, non lasciando che passi per caso.
    assert len(d["morte"]) < d["totale_funzioni"], "tutto morto = misura rotta"


def test_a11y_e_misurata():
    d = _carica("a11y_baseline.json")
    totale = sum(sum(r.values()) for r in d["rotte"].values())
    assert d["rotte"], "nessuna rotta censita"
    assert totale > 20, (
        f"solo {totale} violazioni note: la prima misura ne trovo' 99 su dieci "
        "rotte. Un crollo simile o e' una correzione vera — e allora si "
        "aggiorna questo numero — o e' uno scanner che non ha girato."
    )


def test_mutanti_sono_misurati():
    d = _carica("mutation_baseline.json")
    # ⚠️ I conteggi sono PER MODULO e il totale e' la loro somma.
    #
    # Erano due numeri unici, e una passata mirata (`--modulo fx_service`) li
    # sovrascriveva coi propri: il file diceva «27 mutanti» invece di 130 e
    # questo test diventava rosso su un dato corretto ma parziale. Tenendoli
    # per modulo, una mirata aggiorna solo la propria voce.
    per_modulo = d["per_modulo"]
    assert len(per_modulo) >= 3, "troppo pochi moduli misurati"
    totale = sum(v["mutanti"] for v in per_modulo.values())
    uccisi = sum(v["uccisi"] for v in per_modulo.values())
    assert totale > 50, "troppo pochi mutanti per essere una passata vera"
    assert uccisi > 0, (
        "zero uccisi significa che la suite bersaglio non girava: ogni mutante "
        "sarebbe 'sopravvissuto' e il numero non direbbe niente sui test."
    )
    # ⚠️ E nemmeno tutti uccisi: 43 su 130 e' la misura reale, e un 100%
    # improvviso su questi moduli sarebbe piu' probabilmente un bersaglio
    # sbagliato che un trionfo.
    assert len(d["sopravvissuti"]) > 0


@pytest.mark.parametrize("nome", [
    "dead_code_baseline.json", "a11y_baseline.json", "mutation_baseline.json",
])
def test_ogni_linea_di_base_dice_perche_esiste(nome):
    """Un arretrato senza la sua ragione diventa un obiettivo da azzerare.

    Entrambi i file contengono voci LEGITTIME (script one-off, rami difensivi,
    link di testo in tabelle dense). Chi li trova fra sei mesi deve leggere
    perche' non sono zero, o li «correggera'» cancellandoli.
    """
    d = _carica(nome)
    assert len(d.get("_perche", "")) > 80, f"{nome}: manca la spiegazione"


def test_ogni_arretrato_porta_il_suo_denominatore():
    """⚠️ Un arretrato senza scala non e' un'informazione.

    «63 mutanti sopravvissuti» significa una cosa su 130 generati e un'altra su
    1.300. La scheda rende «non dichiarato» quando il totale manca, ed e' la
    resa corretta — ma qui il totale ESISTE e veniva perso: `mutanti_sopravvissuti`
    leggeva `totale_mutanti`, chiave che il passaggio al cricchetto per modulo
    aveva sostituito con `per_modulo`. `.get` ha risposto None in silenzio.

    Nessun test era rosso, perche' nessuno guardava il denominatore: la rinomina
    ha spezzato un lettore in un ALTRO modulo. Questo test guarda tutti e tre
    gli arretrati insieme, cosi' la prossima rinomina si ferma qui.
    """
    from app.services import verification_posture as vp

    """⚠️ `totale` non e' sempre un denominatore, e la scheda lo sa.

    Per il codice morto e i mutanti e' l'insieme da cui il numeratore e' tratto
    («357 su 1.388 censite»), quindi deve contenerlo. Per l'a11y e' l'AMPIEZZA
    della misura — «103 su 10 rotte» — e 103 su 10 e' la lettura giusta, non un
    errore. Il campo `unita` accanto e' cio' che distingue i due casi a schermo,
    e il test deve fare la stessa distinzione invece di imporre la piu' stretta
    delle due a entrambi.
    """
    for nome, fn, contiene in (
        ("codice morto", vp.codice_mai_eseguito, True),
        ("mutanti", vp.mutanti_sopravvissuti, True),
        ("a11y", vp.violazioni_a11y, False),
    ):
        a = fn()
        assert a is not None, f"{nome}: nessun arretrato letto"
        assert a.totale is not None, f"{nome}: denominatore perso"
        assert a.totale > 0, f"{nome}: totale a zero"
        if contiene:
            assert a.totale >= a.conteggio, (
                f"{nome}: {a.conteggio} su {a.totale} — il numeratore supera il totale"
            )
        assert a.perche, f"{nome}: un arretrato senza ragione scritta e' una lista di difetti"
