"""La valutazione dello scan nel seme del gate (FA-074).

Il seme esegue la meta' dello scan che NON scarica, cosi' che all'avvio del
backend del gate non parta lo scan di recupero — che scaricava barre vere per i
ticker del seme e le incollava sopra la storia sintetica, facendo cambiare le
pagine con la rete.

Il presidio del codice mai eseguito l'ha segnalata come funzione nuova senza
test, ed era giusto: gira nel job del gate, ma nessuna asserzione ne fissava
il contratto. Il test sostituisce le due fasi con dei registratori, perche' la
valutazione vera ha il proprio collaudo altrove e qui interessa COSA viene
chiamato e in che ordine.
"""

from app.scripts import seed_e2e
from app.services import scan_runner, setup_service


def test_valuta_prima_e_chiude_il_giro_come_il_cron(db, monkeypatch):
    ordine: list[tuple] = []

    monkeypatch.setattr(
        scan_runner, "run_tracked_scan",
        lambda sessione, *, trigger: ordine.append(("valuta", trigger)),
    )
    monkeypatch.setattr(
        setup_service, "run_post_scan_bookkeeping",
        lambda sessione, *, universe: ordine.append(("contabilita", universe)),
    )

    seed_e2e.valuta_senza_rete(db)

    # ⚠️ La contabilita' DOPO la valutazione: prima non ci sarebbe niente da
    # chiudere, e i setup appena rilevati non esisterebbero ancora.
    assert [passo for passo, _ in ordine] == ["valuta", "contabilita"]
    # Il perimetro e' l'universo: `run_tracked_scan` valuta l'intero catalogo
    # seminato, come la fase di valutazione del cron (vedi il censimento dei
    # chiamanti in `test_post_scan_perimetro.py`).
    assert ordine[1] == ("contabilita", True)
    # Un trigger riconoscibile nella diagnostica, non «cron» ne' «manual».
    assert ordine[0] == ("valuta", "e2e-seed")


def test_non_passa_dal_percorso_che_scarica():
    """Il contratto che da' il nome alla funzione, controllato sulla SORGENTE.

    ⚠️ La prima stesura di questo test sostituiva entrambe le fasi e poi
    verificava che `fetch_and_upsert` non fosse chiamato: vero di niente, perche'
    con le fasi finte non poteva esserlo in nessun caso. Il rischio reale e' un
    altro — che qualcuno «semplifichi» chiamando il job del cron, che scarica
    prima di valutare — e quello si vede leggendo la funzione.
    """
    import inspect

    sorgente = inspect.getsource(seed_e2e.valuta_senza_rete)
    corpo = sorgente.split('"""')[-1]  # senza il docstring, che li NOMINA

    assert "run_tracked_scan" in corpo
    assert "run_scan_alerts" not in corpo
    assert "fetch_and_upsert" not in corpo
