"""L'addestramento dei due modelli in ombra, sulle barre gia' nel catalogo.

Rifa' in piccolo le due misure dello studio del 2026-09-23 che hanno retto:

  volatilita'  bersaglio log(escursione media delle 10 sedute successive / ATR
               di oggi), cioe' «di quanto l'ATR sbaglia». La base da battere e'
               zero: l'ATR di oggi e' la previsione che il motore fa.
  selezione    fra TUTTI i match dei detector (prima dei cancelli), quali
               battono lo stesso piano giocato su un titolo a caso lo stesso
               giorno. L'etichetta dello studio (`sk`), non «il trade vince»:
               quella premia i target vicini (§6 dello studio).

Il campione e' un sottoinsieme di titoli scelto a caso, e le date sono una ogni
`passo` sedute: tutto il catalogo, ogni giorno, e' il replay di ore dello
studio, che su un nodo solo condiviso con Postgres e Prometheus non si fa la
domenica mattina. Le metriche dell'ultimo anno, tenuto da parte con un embargo,
viaggiano col modello: dicono se QUESTO addestramento ha riprodotto lo studio
prima ancora che arrivi un esito dal vivo.

⚠️ Il match si registra una volta sola: si tengono quelli la cui data del
segnale cade nelle ultime `passo` sedute della finestra, cosi' un segnale che
persiste non viene contato a ogni campione — la stessa ragione del cooldown
degli alert.
"""
from __future__ import annotations

import json
import math
import time
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import func, select

from app.indicators.atr import atr as atr_serie
from app.ml.caratteristiche import matrice, nomi_volatilita, riga_selezione, riga_volatilita
from app.ml.gbm import GBM

#: La finestra dello scan (`scan_service._load_ohlcv`): il contesto e i
#: detector devono vedere in addestramento cio' che vedono dal vivo.
FINESTRA = 260
#: Le sedute del bersaglio di volatilita'.
H_VOL = 10
#: Anno tenuto da parte per le metriche, e embargo prima di esso: i bersagli
#: guardano fino a 63 sedute avanti, quindi senza embargo le ultime righe di
#: addestramento vedrebbero il periodo di prova.
_PROVA = timedelta(days=365)
_EMBARGO = timedelta(days=100)
#: La quota dei «tenuti» su cui lo studio misura il guadagno.
QUOTA = 0.30
MIN_BARRE = 400


def _barre(db, stock_id: int) -> pd.DataFrame:
    from app.models import OhlcvDaily

    righe = db.execute(
        select(OhlcvDaily.date, OhlcvDaily.open, OhlcvDaily.high, OhlcvDaily.low,
               OhlcvDaily.close, OhlcvDaily.volume)
        .where(OhlcvDaily.stock_id == stock_id).order_by(OhlcvDaily.date)
    ).all()
    # Chiude la transazione di sola lettura: l'addestramento dura un'ora e
    # mezza, e una transazione aperta per tutto quel tempo su Postgres e' una
    # sessione «idle in transaction» che trattiene il vacuum.
    db.rollback()
    df = pd.DataFrame(righe, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = df["date"].astype(str).str.slice(0, 10)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def titoli_con_storia(db, minimo: int = MIN_BARRE) -> list[int]:
    from app.models import OhlcvDaily

    return sorted(int(s) for (s,) in db.execute(
        select(OhlcvDaily.stock_id).group_by(OhlcvDaily.stock_id)
        .having(func.count() >= minimo)
    ).all())


# ─── i dati ────────────────────────────────────────────────────────────────

def righe_volatilita(df: pd.DataFrame, *, passo: int, dal: str) -> list[tuple[str, dict, float]]:
    """(data, variabili, bersaglio) ogni `passo` sedute da `dal` in poi."""
    from app.signals.contesto_emissione import contesto

    out = []
    alto, basso = df["high"].to_numpy(), df["low"].to_numpy()
    for t in range(FINESTRA - 1, len(df) - H_VOL, passo):
        if df["date"].iat[t] < dal:
            continue
        ctx = contesto(df.iloc[t - FINESTRA + 1:t + 1])
        a_pct, c = ctx.get("atr_pct"), float(df["close"].iat[t])
        if not a_pct or c <= 0:
            continue
        esc = float(np.nanmean(alto[t + 1:t + 1 + H_VOL] - basso[t + 1:t + 1 + H_VOL]))
        y = math.log(esc / (a_pct * c)) if esc > 0 else math.nan
        if math.isfinite(y):
            out.append((df["date"].iat[t], riga_volatilita(ctx), y))
    return out


def _gara_r(piano, barre, orizzonte: int) -> float | None:
    from app.services.plan_outcome_service import corri_la_gara

    esito = corri_la_gara(piano, barre, orizzonte)
    return None if esito is None else float(esito.r_multiplo)


def _barre_gara(df: pd.DataFrame, da: int, n: int) -> list:
    from app.services.plan_outcome_service import Barra

    sub = df.iloc[da:da + n]
    return [Barra(d, float(h), float(lo), float(c))
            for d, h, lo, c in zip(sub["date"], sub["high"], sub["low"], sub["close"], strict=True)]


def _piano_di_controllo(piano, atr_o: float, entry_o: float, atr: float):
    """Lo stesso piano in unita' del SUO ATR su un altro titolo: stessa
    direzione, stesso stop in ATR, stessi rapporti dei target."""
    from app.signals.trade_plan import PianoDiTrade, Target

    r_o = piano.r / atr * atr_o
    segno = 1.0 if piano.side == "long" else -1.0
    return PianoDiTrade(
        side=piano.side, horizon=piano.horizon, entry=entry_o, stop=entry_o - segno * r_o,
        stop_pct=r_o / entry_o * 100.0, stop_capped=False, r=r_o,
        targets=[Target(t.label, entry_o + segno * t.rr * r_o, t.rr) for t in piano.targets],
    )


def righe_selezione(
    serie: dict[int, pd.DataFrame], *, passo: int, dal: str, rng: np.random.Generator,
) -> list[dict]:
    """Un dizionario per match: data, variabili, R, R del controllo."""
    from app.services.signal_drift_service import _horizon_days
    from app.signals.contesto_emissione import contesto
    from app.signals.horizon import classify_horizon
    from app.signals.runner import detect_signals
    from app.signals.trade_plan import costruisci_piano

    indici = {s: {d: i for i, d in enumerate(df["date"])} for s, df in serie.items()}
    atr_di = {s: atr_serie(df, 14).to_numpy() for s, df in serie.items()}
    titoli = list(serie)
    out: list[dict] = []
    for s, df in serie.items():
        date_s = df["date"].tolist()
        for t in range(FINESTRA - 1 + passo, len(df), passo):
            if date_s[t] < dal:
                continue
            win = df.iloc[t - FINESTRA + 1:t + 1].reset_index(drop=True)
            try:
                matches = detect_signals(win)
            except Exception:  # noqa: BLE001 — un titolo non ferma l'addestramento
                continue
            freschi = [m for m in matches if date_s[t - passo] < str(m.signal_date)[:10] <= date_s[t]]
            if not freschi:
                continue
            ctx = contesto(win)
            close = float(df["close"].iat[t])
            atr = float(atr_serie(win, 14).iat[-1])
            if not (atr > 0 and close > 0):
                continue
            for m in freschi:
                hz = classify_horizon(m.name, m.chain)
                piano = costruisci_piano(
                    {"tone": m.tone, "atr": atr, "invalidation": m.invalidation, "horizon": hz},
                    close, m.name)
                H = _horizon_days(m.name)
                if piano is None or t + H >= len(df):
                    continue
                R = _gara_r(piano, _barre_gara(df, t + 1, H), H)
                if R is None:
                    continue
                # Il controllo: un altro titolo del campione quotato quel giorno
                # con H sedute dopo. Fino a cinque tentativi, poi si rinuncia.
                Rc = None
                for _ in range(5):
                    o = titoli[int(rng.integers(len(titoli)))]
                    j = indici[o].get(date_s[t])
                    if o == s or j is None or j + H >= len(serie[o]):
                        continue
                    a_o, c_o = float(atr_di[o][j]), float(serie[o]["close"].iat[j])
                    if not (a_o > 0 and c_o > 0):
                        continue
                    Rc = _gara_r(_piano_di_controllo(piano, a_o, c_o, atr),
                                 _barre_gara(serie[o], j + 1, H), H)
                    break
                if Rc is None:
                    continue
                out.append({
                    "date": date_s[t], "detector": m.name, "strength": float(m.strength),
                    "R": R, "Rc": Rc,
                    "x": riga_selezione(detector=m.name, tone=m.tone, horizon=hz,
                                        strength=m.strength, factors=m.factors, ctx=ctx,
                                        stop_atr=piano.r / atr, rr=piano.targets[0].rr),
                })
    return out


# ─── i modelli ─────────────────────────────────────────────────────────────

def _t_mensile(valori: pd.Series) -> float | None:
    v = valori.dropna()
    if len(v) < 3 or v.std(ddof=1) == 0:
        return None
    return float(v.mean() / (v.std(ddof=1) / math.sqrt(len(v))))


def _auc(y: np.ndarray, s: np.ndarray) -> float | None:
    y = np.asarray(y, bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return None
    r = pd.Series(s).rank().to_numpy()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _gbm_vol(seed: int) -> GBM:
    return GBM(n_trees=200, depth=3, lr=0.05, min_leaf=200, loss="l2", seed=seed)


def _gbm_sel(n: int, seed: int) -> GBM:
    return GBM(n_trees=250, depth=3, lr=0.03, min_leaf=max(100, n // 300), l2=10.0, seed=seed)


def modello_volatilita(righe: list[tuple[str, dict, float]], *, taglio: str, seme: int = 0) -> tuple[dict, dict]:
    """(artefatto, metriche). Metriche sull'anno dopo `taglio`, modello su tutto."""
    nomi = nomi_volatilita()
    date_ = np.array([d for d, _, _ in righe])
    X = matrice([x for _, x, _ in righe], nomi)
    y = np.array([v for _, _, v in righe])
    inizio_prova = taglio
    fine_addestr = (date.fromisoformat(taglio) - _EMBARGO).isoformat()
    tr, te = date_ < fine_addestr, date_ >= inizio_prova
    metriche: dict = {"righe": int(len(y)), "righe_prova": int(te.sum()), "dal_prova": inizio_prova}
    if tr.sum() >= 1000 and te.sum() >= 200:
        g = _gbm_vol(seme).fit(X[tr], y[tr])
        p = g.predict(X[te])
        sse = float(((y[te] - p) ** 2).sum())
        metriche["R2_contro_ATR"] = round(1 - sse / float((y[te] ** 2).sum()), 4)
        metriche["R2_contro_media"] = round(1 - sse / float(((y[te] - y[tr].mean()) ** 2).sum()), 4)
    g = _gbm_vol(seme).fit(X, y)
    return {"gbm": g.to_dict(), "nomi": nomi, "bersaglio": f"log(escursione {H_VOL}g / ATR)"}, metriche


def _nomi_selezione(righe: list[dict]) -> list[str]:
    conteggio: dict[str, int] = {}
    for r in righe:
        for k in r["x"]:
            conteggio[k] = conteggio.get(k, 0) + 1
    n = max(len(righe), 1)
    return sorted(k for k, c in conteggio.items()
                  if k.startswith("det_") or not k.startswith("fac_") or c / n >= 0.01)


def modello_selezione(righe: list[dict], *, taglio: str, seme: int = 0) -> tuple[dict, dict]:
    nomi = _nomi_selezione(righe)
    date_ = np.array([r["date"] for r in righe])
    X = matrice([r["x"] for r in righe], nomi, zero_se_manca=("det_",))
    skill = np.array([r["R"] - r["Rc"] for r in righe])
    y = (skill > 0).astype(float)
    forza = np.array([r["strength"] for r in righe])
    fine_addestr = (date.fromisoformat(taglio) - _EMBARGO).isoformat()
    tr, te = date_ < fine_addestr, date_ >= taglio
    metriche: dict = {"righe": int(len(y)), "righe_prova": int(te.sum()), "dal_prova": taglio,
                      "base": round(float(y.mean()), 4) if len(y) else None}
    if tr.sum() >= 2000 and te.sum() >= 200:
        g = _gbm_sel(int(tr.sum()), seme).fit(X[tr], y[tr])
        p_tr, p_te = g.predict(X[tr]), g.predict(X[te])
        soglia = float(np.quantile(p_tr, 1 - QUOTA))
        soglia_f = float(np.quantile(forza[tr], 1 - QUOTA))
        mese = pd.Series(date_[te]).str.slice(0, 7).to_numpy()
        sk_te = skill[te]
        guadagno = pd.Series(np.where(p_te >= soglia, sk_te, np.nan)).groupby(mese).mean() \
            - pd.Series(sk_te).groupby(mese).mean()
        guadagno_f = pd.Series(np.where(forza[te] >= soglia_f, sk_te, np.nan)).groupby(mese).mean() \
            - pd.Series(sk_te).groupby(mese).mean()
        metriche.update({
            "auc": _auc(y[te], p_te),
            "auc_forza": _auc(y[te], forza[te]),
            "skill_tutti": round(float(sk_te.mean()), 4),
            "skill_top30": round(float(sk_te[p_te >= soglia].mean()), 4) if (p_te >= soglia).any() else None,
            "skill_top30_forza": round(float(sk_te[forza[te] >= soglia_f].mean()), 4)
            if (forza[te] >= soglia_f).any() else None,
            "guadagno_mensile": round(float(guadagno.mean()), 4) if guadagno.notna().any() else None,
            "t_mensile": _t_mensile(guadagno),
            "t_mensile_forza": _t_mensile(guadagno_f),
            "mesi": int(guadagno.notna().sum()),
        })
    g = _gbm_sel(len(y), seme).fit(X, y)
    soglia_tutti = float(np.quantile(g.predict(X), 1 - QUOTA))
    return ({"gbm": g.to_dict(), "nomi": nomi, "soglia_top30": soglia_tutti,
             "etichetta": "R - R del controllo casuale > 0"}, metriche)


# ─── il giro completo ──────────────────────────────────────────────────────

def addestra(
    db, *, n_titoli_vol: int = 300, n_titoli_sel: int = 80, passo_vol: int = 10,
    passo_sel: int = 10, anni: int = 9, seme: int | None = None,
    adesso: datetime | None = None, salva: bool = True,
    min_righe_vol: int = 1000, min_righe_sel: int = 2000,
) -> dict:
    """Addestra e salva entrambi i modelli. Rende le metriche."""
    from app.ml import ombra
    from app.models.modello_ombra import ModelloOmbra

    adesso = adesso or datetime.now(UTC)
    seme = int(adesso.strftime("%Y%m%d")) if seme is None else seme
    rng = np.random.default_rng(seme)
    dal = (adesso.date() - timedelta(days=365 * anni)).isoformat()
    taglio = (adesso.date() - _PROVA).isoformat()
    titoli = titoli_con_storia(db)
    if len(titoli) < 3:
        logger.info("[ombra] catalogo senza storia sufficiente: niente addestramento")
        return {}
    rng.shuffle(titoli)
    t0 = time.monotonic()
    risultato: dict = {}

    vol: list = []
    for s in titoli[:n_titoli_vol]:
        vol += righe_volatilita(_barre(db, s), passo=passo_vol, dal=dal)
    if len(vol) >= min_righe_vol:
        art, met = modello_volatilita(vol, taglio=taglio, seme=seme)
        met["titoli"] = min(n_titoli_vol, len(titoli))
        risultato["volatilita"] = (art, met)
    logger.info(f"[ombra] volatilita': {len(vol)} righe in {time.monotonic() - t0:.0f}s")

    t1 = time.monotonic()
    serie = {s: _barre(db, s) for s in titoli[:n_titoli_sel]}
    sel = righe_selezione(serie, passo=passo_sel, dal=dal, rng=rng)
    del serie
    if len(sel) >= min_righe_sel:
        art, met = modello_selezione(sel, taglio=taglio, seme=seme)
        met["titoli"] = min(n_titoli_sel, len(titoli))
        risultato["selezione"] = (art, met)
    logger.info(f"[ombra] selezione: {len(sel)} match in {time.monotonic() - t1:.0f}s")

    versione = adesso.strftime("%Y-%m-%dT%H%M")
    metriche = {nome: met for nome, (_, met) in risultato.items()}
    if salva:
        for nome, (art, met) in risultato.items():
            db.add(ModelloOmbra(nome=nome, versione=versione, addestrato_il=adesso,
                                artefatto=json.dumps(art), metriche=json.dumps(met)))
        db.commit()
        ombra.dimentica()
    logger.info(f"[ombra] addestramento {versione}: {json.dumps(metriche)}")
    return metriche


def serve_addestrare(db, *, adesso: datetime | None = None, giorni: int = 27) -> bool:
    """Vero se manca un modello o il piu' recente ha piu' di `giorni` giorni."""
    from app.models.modello_ombra import ModelloOmbra

    adesso = adesso or datetime.now(UTC)
    for nome in ("volatilita", "selezione"):
        ultimo = db.execute(
            select(func.max(ModelloOmbra.addestrato_il)).where(ModelloOmbra.nome == nome)
        ).scalar()
        if ultimo is None:
            return True
        if ultimo.tzinfo is None:
            ultimo = ultimo.replace(tzinfo=UTC)
        if adesso - ultimo > timedelta(days=giorni):
            return True
    return False
