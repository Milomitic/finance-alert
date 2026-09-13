"""Il seme del gate e2e non deve dipendere da QUANDO gira.

⚠️ Il seme esiste per rendere il gate RIPETIBILE — CLAUDE.md lo dice gia' a
proposito di `/calendar`, che sbordava in CI e non in locale perche' il
database locale aveva dati diversi: «una misura che dipende da cosa c'e' nel
database non e' una misura». Il generatore casuale era seminato e la frase
sembrava rispettata. Non lo era: la dipendenza non era dai DATI ma
dall'OROLOGIO, e ha fatto arrossare il gate su due rotte che il commit non
aveva toccato.

Due canali, entrambi chiusi qui:

1. **Le barre.** Contando i feriali dentro un intervallo fisso di giorni, il
   numero di barre dipende da che giorno della settimana e' oggi — 215 il
   sabato, 214 il lunedi'. Ogni barra consuma un'estrazione, quindi una barra
   in meno sposta TUTTA la serie di prezzi: le percentuali a schermo cambiano,
   e con esse i colori. Cosi' `/sectors` ha guadagnato una violazione di
   contrasto in una notte.

2. **L'ancora dei segnali.** Era `datetime.now(UTC)`. Gli scarti valgono fino a
   78 ore, quindi lo scarto in GIORNI DI CALENDARIO fra `signal_date` e
   `triggered_at` cambiava con l'ora della corsa — e quella soglia decide la
   pastiglia «in ritardo», cioe' quanti elementi la pagina rende. Il job che ha
   fallito girava alle 00:18 UTC.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.scripts.seed_e2e import BARRE, _ancora, _giorni_feriali

#: Una settimana intera di «oggi» possibili, piu' un 29 febbraio.
GIORNI = [date(2026, 9, 14) + timedelta(days=k) for k in range(7)] + [date(2024, 2, 29)]


@pytest.mark.parametrize("oggi", GIORNI, ids=lambda d: d.strftime("%a-%Y-%m-%d"))
def test_sempre_lo_stesso_numero_di_barre(oggi):
    giorni = _giorni_feriali(oggi, BARRE)
    assert len(giorni) == BARRE
    assert all(g.weekday() < 5 for g in giorni), "c'e' un weekend fra le barre"
    assert giorni == sorted(giorni), "le barre non sono in ordine crescente"
    assert len(set(giorni)) == BARRE, "ci sono date ripetute"
    assert giorni[-1] < oggi, "l'ultima barra non e' nel passato"


def test_il_controllo_negativo_la_vecchia_forma_NON_era_stabile():
    """⚠️ Senza questo, il test sopra sembra una formalita'.

    Fissa il difetto che la correzione ha chiuso: contare i feriali DENTRO un
    intervallo fisso di giorni da un numero che dipende dal giorno della
    settimana. Se un giorno qualcuno «semplificasse» `_giorni_feriali`
    tornando a quella forma, il test sopra diventerebbe rosso e questo dice
    perche'.
    """
    vecchia = {
        sum(1 for i in range(BARRE, 0, -1) if (o - timedelta(days=i)).weekday() < 5)
        for o in GIORNI
    }
    assert len(vecchia) > 1, (
        "la vecchia formulazione sembra stabile: il controllo non prova piu' niente"
    )


@pytest.mark.parametrize("oggi", GIORNI, ids=lambda d: d.strftime("%a-%Y-%m-%d"))
def test_lo_scarto_fra_segnale_e_scatto_non_dipende_dall_ora(oggi):
    """La grandezza che la UI legge e' lo scarto in GIORNI, non gli istanti.

    Si ricalcola qui la stessa aritmetica del seme — scarto in ore per lo
    scatto, scarto in giorni per la data del segnale — e si verifica che la
    differenza in giorni di calendario sia la stessa per ogni «oggi». Con
    `datetime.now(UTC)` al posto dell'ancora, questo valore cambiava con l'ora
    in cui il job partiva.
    """
    scarti = []
    for i in range(12):
        for j in range(3):
            scattato = _ancora(oggi) - timedelta(hours=6 * (i + j))
            segnale = oggi - timedelta(days=1 + (i + j) % 5)
            scarti.append((scattato.date() - segnale).days)
    assert scarti == RIFERIMENTO, (
        "lo scarto segnale→scatto e' cambiato: la pastiglia «in ritardo» "
        "comparirebbe su un numero diverso di righe a seconda del giorno."
    )


def _riferimento() -> list[int]:
    ancora = datetime.combine(date(2026, 1, 7), datetime.min.time(), tzinfo=UTC).replace(hour=12)
    base = date(2026, 1, 7)
    return [
        ((ancora - timedelta(hours=6 * (i + j))).date() - (base - timedelta(days=1 + (i + j) % 5))).days
        for i in range(12)
        for j in range(3)
    ]


RIFERIMENTO = _riferimento()


def test_mezzogiorno_e_lontano_da_entrambi_i_bordi():
    """L'ancora deve stare lontano dalla mezzanotte in ENTRAMBE le direzioni:
    e' l'unica proprieta' che rende irrilevante l'ora della corsa."""
    a = _ancora(date(2026, 9, 13))
    assert a.tzinfo is not None, "un'ancora senza fuso e' ambigua"
    assert a.hour == 12 and a.minute == 0
