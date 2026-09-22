"""La geometria del piano in Python deve rendere gli STESSI numeri del TS.

`frontend/src/lib/tradePlaybook.ts` e' cio' che l'utente vede a schermo; il
gemello Python serve a far correre stop e target sulle barre per l'esito
basato sul piano. Due copie della stessa aritmetica divergono al primo
ritocco — in questo repo e' gia' successo con `_posture`, duplicata fra
`finalize` e `recompute_one`, e ha prodotto un 500 in produzione.

Qui la divergenza sarebbe piu' insidiosa di un 500: si misurerebbe un piano
DIVERSO da quello mostrato, e i due numeri sarebbero entrambi plausibili.

Il legame e' `frontend/src/lib/playbookVectors.json`, generato dal TS e letto
da entrambi i lati. Chi tocca una meta' sola rende rosso il test dell'altra.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.signals.trade_plan import costruisci_piano

VETTORI = (Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib"
           / "playbookVectors.json")


def _casi() -> list[dict]:
    # ⚠️ Un file mancante deve FALLIRE, non far saltare i test: un ponte fra
    # due implementazioni che si salta da solo quando l'altra meta' non c'e'
    # e' esattamente il ponte che non regge nel momento in cui servirebbe.
    assert VETTORI.exists(), (
        f"vettori d'oro assenti: {VETTORI}. Sono generati dal TS e "
        f"versionati; senza, questo test non verifica nulla."
    )
    return json.loads(VETTORI.read_text(encoding="utf-8"))["casi"]


def test_i_vettori_coprono_i_casi_limite_e_non_solo_quelli_facili() -> None:
    """Pavimento sul contenuto del ponte.

    Senza, svuotare il file renderebbe verdi tutti i confronti qui sotto — la
    forma «un test puo' essere vero di niente» che questo repo ha gia'
    registrato quattro volte.
    """
    nomi = {c["nome"] for c in _casi()}
    for atteso in ("long_breve", "short_breve", "stop_al_pavimento", "stop_al_tetto",
                   "senza_atr_ripiego_2pct", "target_degeneri_tp2_uguale_tp1",
                   "senza_invalidazione_nessun_piano",
                   "ingressi_congelati_battono_i_correnti"):
        assert atteso in nomi, f"manca il caso limite «{atteso}»"
    assert len(nomi) >= 14


@pytest.mark.parametrize("caso", _casi(), ids=lambda c: c["nome"])
def test_il_gemello_python_rende_gli_stessi_numeri_del_ts(caso: dict) -> None:
    piano = costruisci_piano(caso["snapshot"], caso["entry"], caso["name"])
    atteso = caso["atteso"]

    if atteso is None:
        assert piano is None, "il TS non produce un piano qui, il Python si'"
        return

    assert piano is not None, "il TS produce un piano qui, il Python no"
    assert piano.side == atteso["side"]
    assert piano.horizon == atteso["horizon"]
    assert piano.stop_capped is atteso["stopCapped"]
    # Tolleranza da virgola mobile, non da approssimazione: i due linguaggi
    # fanno la stessa aritmetica IEEE 754 e devono combaciare fino all'ultimo
    # bit utile. 1e-9 lascia passare solo il rumore dell'ordine delle
    # operazioni, non una formula diversa.
    assert piano.entry == pytest.approx(atteso["entry"], abs=1e-9)
    assert piano.stop == pytest.approx(atteso["stop"], abs=1e-9)
    assert piano.stop_pct == pytest.approx(atteso["stopPct"], abs=1e-9)
    assert len(piano.targets) == len(atteso["targets"])
    for mio, suo in zip(piano.targets, atteso["targets"], strict=True):
        assert mio.price == pytest.approx(suo["price"], abs=1e-9)
        assert mio.rr == pytest.approx(suo["rr"], abs=1e-9)


def test_il_moltiplicatore_R_del_target_NON_e_una_costante() -> None:
    """⚠️ Serve a fissare un fatto che si tende a dare per scontato.

    Sarebbe naturale dire «TP1 vale +4R» perche' `tp1R` vale 4.0 sull'orizzonte
    breve. Ma i target sono anche TAGLIATI a un multiplo di ATR, quindi l'R
    realizzato varia per segnale: nei vettori va da 0,2 a 4,0. Un esito che
    assumesse un R costante scriverebbe numeri sbagliati su ogni riga dove il
    taglio morde, ed e' proprio per questo che l'R va REGISTRATO trade per
    trade invece che dedotto dal detector.
    """
    rr = [t["rr"] for c in _casi() if c["atteso"] for t in c["atteso"]["targets"]]
    assert min(rr) < 1.0, "nessun caso col target piu' vicino dello stop"
    assert max(rr) >= 4.0, "nessun caso col target a pieno multiplo di R"


def test_lo_stop_sta_sempre_dalla_parte_che_fa_perdere() -> None:
    for caso in _casi():
        piano = costruisci_piano(caso["snapshot"], caso["entry"], caso["name"])
        if piano is None:
            continue
        if piano.side == "long":
            assert piano.stop < piano.entry
            assert all(t.price > piano.entry for t in piano.targets)
        else:
            assert piano.stop > piano.entry
            assert all(t.price < piano.entry for t in piano.targets)
