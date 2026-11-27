"""Cali dal massimo e recuperi (FA-185, FA-198).

Un calo («drawdown») comincia a un massimo di chiusura, tocca un minimo, e
finisce quando la chiusura torna al massimo di partenza. Se non ci torna, il
calo e' ancora aperto e lo si dice: `recupero` None.

Tutto su chiusure: un minimo intraday piu' profondo esiste, ma il resto
dell'app (52 settimane, range) misura sulle chiusure, e due definizioni dello
stesso «minimo» nella stessa pagina sono la forma di difetto che il progetto
ha gia' pagato (FA-030).
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date


def episodi(date_: Sequence[date], chiusure: Sequence[float], soglia: float = 0.10) -> list[dict]:
    """I cali con profondita' almeno `soglia` (0,10 = 10%), dal piu' recente.

    Ogni episodio: picco, minimo, recupero (date ISO, recupero None se
    aperto), profondita' (negativa), sedute di discesa e di recupero."""
    out: list[dict] = []
    if len(chiusure) < 2:
        return out
    i_picco = 0
    i_minimo = 0
    in_calo = False
    for i in range(1, len(chiusure)):
        c = chiusure[i]
        if c <= 0:
            continue
        if c >= chiusure[i_picco]:
            if in_calo:
                prof = chiusure[i_minimo] / chiusure[i_picco] - 1.0
                if -prof >= soglia:
                    out.append(_episodio(date_, chiusure, i_picco, i_minimo, i))
            i_picco = i_minimo = i
            in_calo = False
        else:
            # Sotto il picco: il minimo parte dal picco stesso, quindi il
            # primo giorno di calo lo aggiorna sempre.
            in_calo = True
            if c < chiusure[i_minimo]:
                i_minimo = i
    if in_calo:
        prof = chiusure[i_minimo] / chiusure[i_picco] - 1.0
        if -prof >= soglia:
            out.append(_episodio(date_, chiusure, i_picco, i_minimo, None))
    return list(reversed(out))


def _episodio(date_, chiusure, i_picco: int, i_minimo: int, i_recupero: int | None) -> dict:
    return {
        "picco": date_[i_picco].isoformat(),
        "minimo": date_[i_minimo].isoformat(),
        "recupero": date_[i_recupero].isoformat() if i_recupero is not None else None,
        "profondita": chiusure[i_minimo] / chiusure[i_picco] - 1.0,
        "sedute_discesa": i_minimo - i_picco,
        "sedute_recupero": (i_recupero - i_minimo) if i_recupero is not None else None,
    }


def calo_corrente(date_: Sequence[date], chiusure: Sequence[float]) -> dict | None:
    """Quanto l'ultima chiusura dista dal massimo storico, e da quando."""
    if not chiusure:
        return None
    i = max(range(len(chiusure)), key=lambda k: chiusure[k])
    if chiusure[i] <= 0:
        return None
    return {"profondita": chiusure[-1] / chiusure[i] - 1.0, "picco": date_[i].isoformat(),
            "sedute_dal_picco": len(chiusure) - 1 - i}


def calo_massimo(date_: Sequence[date], chiusure: Sequence[float], sedute: int | None = None) -> dict | None:
    """Il calo piu' profondo nelle ultime `sedute` (None = tutta la storia),
    con picco, minimo e recupero se avvenuto entro la serie."""
    if len(chiusure) < 2:
        return None
    da = 0 if sedute is None else max(0, len(chiusure) - sedute)
    d, c = date_[da:], chiusure[da:]
    i_picco_corr = 0
    peggiore = (0.0, 0, 0)  # profondita', picco, minimo
    for i in range(1, len(c)):
        if c[i] > c[i_picco_corr]:
            i_picco_corr = i
        elif c[i_picco_corr] > 0:
            prof = c[i] / c[i_picco_corr] - 1.0
            if prof < peggiore[0]:
                peggiore = (prof, i_picco_corr, i)
    prof, ip, im = peggiore
    if prof == 0.0:
        return {"profondita": 0.0, "picco": None, "minimo": None, "recupero": None}
    rec = next((k for k in range(im + 1, len(c)) if c[k] >= c[ip]), None)
    return {"profondita": prof, "picco": d[ip].isoformat(), "minimo": d[im].isoformat(),
            "recupero": d[rec].isoformat() if rec is not None else None}
