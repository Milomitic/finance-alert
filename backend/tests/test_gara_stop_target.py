"""La gara fra stop e target: chi viene toccato PRIMA, barra per barra.

Risponde a una domanda diversa da `abs_hit`, e le due non vanno confuse:

    abs_hit        il detector prevede la deriva a orizzonte fisso?
    questa gara    il piano mostrato a schermo avrebbe pagato?

La seconda e' quella che un utente vive: una posizione con un ordine limite al
target si chiude DA SOLA quando il prezzo lo tocca, e cosa fa il prezzo alla
63a seduta non cambia il conto. Misurarla sulla chiusura finale e' rispondere
a un'altra domanda.

⚠️ Ed e' una GARA, non un «ha mai toccato il target». Una posizione con quelle
caratteristiche ha anche uno stop, e si sarebbe chiusa da sola in PERDITA se
lo stop arrivava prima. Contare i soli tocchi del target produce un tasso di
successo gonfiato per costruzione: quasi tutto tocca un target vicino, prima o
poi.
"""
from __future__ import annotations

import pytest

from app.services.plan_outcome_service import Barra, corri_la_gara
from app.signals.trade_plan import PianoDiTrade, Target


def _piano(side: str = "long", entry: float = 100.0, stop: float = 96.0,
           tp1: float = 108.0, tp2: float = 112.0) -> PianoDiTrade:
    r = abs(entry - stop)
    return PianoDiTrade(
        side=side, horizon="Breve", entry=entry, stop=stop,
        stop_pct=(r / entry) * 100, stop_capped=False, r=r,
        targets=[Target("Target 1", tp1, abs(tp1 - entry) / r),
                 Target("Target 2", tp2, abs(tp2 - entry) / r)],
    )


def _b(giorno: int, alto: float, basso: float, chius: float) -> Barra:
    return Barra(f"2026-03-{giorno:02d}", alto, basso, chius)


# ─── L'esito, e l'ordine in cui si arriva ──────────────────────────────────

def test_il_target_colpito_per_primo_chiude_in_guadagno() -> None:
    barre = [_b(2, 103, 99, 102), _b(3, 109, 101, 108), _b(4, 99, 90, 95)]
    e = corri_la_gara(_piano(), barre, orizzonte=21)
    assert e is not None
    assert e.esito == "tp1"
    assert e.data == "2026-03-03"
    assert e.barre == 2
    # ⚠️ Il crollo della barra dopo NON conta: a quel punto la posizione e'
    # gia' chiusa. E' tutta la differenza con l'etichetta a orizzonte fisso.
    assert e.r_multiplo == pytest.approx(2.0)


def test_lo_stop_colpito_per_primo_chiude_a_meno_un_R() -> None:
    barre = [_b(2, 103, 99, 102), _b(3, 104, 95.5, 96), _b(4, 115, 110, 114)]
    e = corri_la_gara(_piano(), barre, orizzonte=21)
    assert e is not None
    assert e.esito == "stop"
    assert e.r_multiplo == pytest.approx(-1.0)
    assert e.data == "2026-03-03"


def test_stop_e_target_nella_STESSA_barra_sono_ambigui_e_contano_come_stop() -> None:
    """Il dato giornaliero non dice quale sia venuto prima dentro la barra.

    La convenzione e' pessimista — si assegna lo stop — ma l'esito resta una
    CATEGORIA A SE': cosi' dopo si puo' misurare quanto costa la convenzione,
    invece di doverla dare per buona per sempre.
    """
    barre = [_b(2, 109, 95, 104)]
    e = corri_la_gara(_piano(), barre, orizzonte=21)
    assert e is not None
    assert e.esito == "ambigua"
    assert e.r_multiplo == pytest.approx(-1.0)


def test_senza_tocchi_entro_l_orizzonte_si_valorizza_alla_chiusura() -> None:
    barre = [_b(g, 103, 99, 101.5) for g in range(2, 7)]
    e = corri_la_gara(_piano(), barre, orizzonte=5)
    assert e is not None
    assert e.esito == "scaduto"
    assert e.barre == 5
    # (101.5 - 100) / 4 = 0.375R
    assert e.r_multiplo == pytest.approx(0.375)


def test_finche_l_orizzonte_non_e_trascorso_e_nulla_e_stato_toccato_NON_si_etichetta() -> None:
    """⚠️ Un trade giovane e ancora aperto non e' uno «scaduto».

    Etichettarlo vorrebbe dire scrivere un esito che il tempo puo' ancora
    smentire — cioe' esattamente il difetto opposto a quello che stiamo
    chiudendo, con lo stesso segno: un numero prima che ci sia.
    """
    barre = [_b(2, 103, 99, 101), _b(3, 102, 98, 100)]
    assert corri_la_gara(_piano(), barre, orizzonte=21) is None


def test_senza_barre_non_c_e_niente_da_misurare() -> None:
    assert corri_la_gara(_piano(), [], orizzonte=21) is None


# ─── Lo short e' speculare ─────────────────────────────────────────────────

def test_lo_short_corre_al_contrario() -> None:
    piano = _piano(side="short", entry=100.0, stop=104.0, tp1=92.0, tp2=88.0)
    barre = [_b(2, 102, 97, 98), _b(3, 99, 91.5, 92)]
    e = corri_la_gara(piano, barre, orizzonte=21)
    assert e is not None
    assert e.esito == "tp1"
    assert e.r_multiplo == pytest.approx(2.0)


def test_lo_short_va_a_stop_quando_il_prezzo_SALE() -> None:
    piano = _piano(side="short", entry=100.0, stop=104.0, tp1=92.0, tp2=88.0)
    barre = [_b(2, 104.5, 99, 104)]
    e = corri_la_gara(piano, barre, orizzonte=21)
    assert e is not None and e.esito == "stop"


# ─── Il secondo target ─────────────────────────────────────────────────────

def test_il_secondo_target_e_registrato_a_parte_non_al_posto_del_primo() -> None:
    """L'esito primario resta la gara TP1-contro-stop: e' il primo target che
    chiude la posizione nella lettura piu' semplice. Che il prezzo sia arrivato
    anche al secondo e' un'informazione IN PIU', e mescolarla nell'esito
    renderebbe incomparabili le righe."""
    barre = [_b(2, 113, 99, 112)]
    e = corri_la_gara(_piano(), barre, orizzonte=21)
    assert e is not None
    assert e.esito == "tp1"
    assert e.tp2_raggiunto is True


def test_il_secondo_target_NON_si_conta_se_arriva_dopo_lo_stop() -> None:
    barre = [_b(2, 104, 95, 96), _b(3, 120, 110, 118)]
    e = corri_la_gara(_piano(), barre, orizzonte=21)
    assert e is not None
    assert e.esito == "stop"
    assert e.tp2_raggiunto is False


# ─── MAE e MFE: gli ingressi per tarare la geometria ───────────────────────

def test_mae_e_mfe_misurano_quanto_il_trade_e_andato_contro_e_a_favore() -> None:
    """Sono i numeri che dicono se lo stop e' troppo stretto e il target troppo
    lontano, e valgono piu' di un binario per osservazione: sono continui."""
    barre = [_b(2, 104, 97, 103), _b(3, 109, 102, 108)]
    e = corri_la_gara(_piano(), barre, orizzonte=21)
    assert e is not None
    # contro: 100 -> 97 = 3 punti su 4 di R
    assert e.mae_r == pytest.approx(0.75)
    # a favore: 100 -> 109 = 9 punti su 4 di R
    assert e.mfe_r == pytest.approx(2.25)


def test_un_trade_mai_andato_contro_ha_escursione_avversa_ZERO() -> None:
    """⚠️ Non negativa: «massima escursione avversa» con segno meno sarebbe una
    contraddizione, e zero dice la cosa giusta — lo stop non e' mai stato
    avvicinato."""
    barre = [_b(2, 109, 100.5, 108)]
    e = corri_la_gara(_piano(), barre, orizzonte=21)
    assert e is not None
    assert e.mae_r == 0.0


def test_l_escursione_si_ferma_alla_barra_che_RISOLVE() -> None:
    """Dopo la chiusura della posizione il prezzo non e' piu' affar suo."""
    barre = [_b(2, 109, 99, 108), _b(3, 200, 50, 60)]
    e = corri_la_gara(_piano(), barre, orizzonte=21)
    assert e is not None
    assert e.mfe_r == pytest.approx(2.25)   # non 25.0
    assert e.mae_r == pytest.approx(0.25)   # non 12.5


# ─── L'ancora sul caso reale ───────────────────────────────────────────────

def test_il_caso_FLNC_del_28_agosto_si_chiude_al_target_il_14_settembre() -> None:
    """I numeri veri dell'alert 18987 (analyst_momentum, ribassista) e le barre
    vere di FLNC prese dalla produzione.

    E' l'ancora che tiene questa funzione attaccata al caso da cui e' nata: il
    magazzino non lo sapra' prima di fine novembre, e quando lo sapra' leggera'
    la chiusura della 63a seduta invece di questo.
    """
    piano = _piano(side="short", entry=11.43, stop=11.94, tp1=9.40, tp2=8.38)
    reali = [
        ("2026-08-31", 11.10, 10.72), ("2026-09-01", 10.64, 10.34),
        ("2026-09-02", 10.72, 10.24), ("2026-09-03", 10.42, 9.95),
        ("2026-09-04", 10.37, 10.05), ("2026-09-08", 11.37, 10.62),
        ("2026-09-09", 10.87, 10.10), ("2026-09-10", 10.07, 9.64),
        ("2026-09-11", 10.16, 9.76), ("2026-09-14", 9.65, 9.24),
        ("2026-09-15", 9.53, 9.23), ("2026-09-16", 9.60, 8.85),
    ]
    barre = [Barra(d, hi, lo, lo) for d, hi, lo in reali]
    e = corri_la_gara(piano, barre, orizzonte=63)
    assert e is not None
    assert e.esito == "tp1"
    assert e.data == "2026-09-14"
    assert e.r_multiplo > 3.9
