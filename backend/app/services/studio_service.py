"""Statistica storica a schermo (FA-157): tre domande sul passato di un simbolo.

    dopo_movimento   che cosa e' successo nelle H sedute dopo una variazione
                     di almeno X% in N sedute
    stagionalita     il rendimento per mese dell'anno e per giorno della
                     settimana
    evento           il percorso medio attorno alle trimestrali del titolo o
                     ai rilasci di una serie macro

⚠️ Ogni risposta porta le stesse quattro cose, ed e' la regola di onesta' di
tutto il progetto applicata a una domanda libera:

1. i CASI e le FINESTRE INDIPENDENTI (`independent_blocks`): dieci giorni di
   fila che soddisfano la condizione sono un episodio, non dieci;
2. l'INTERVALLO della media, largo quanto le finestre indipendenti giustificano
   (`mean_interval`), o None quando sono meno di due;
3. il CASO BASE: la stessa misura su tutte le finestre della stessa lunghezza.
   «Dopo un calo del 10% il titolo ha fatto +3% in un mese» non dice niente se
   in un mese qualunque ha fatto +2,5%;
4. nessun verdetto di previsione. Lo studio descrive.

Una serie costante rende zero casi e non una media (FA-157, test).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.stats import calendario as cal
from app.stats.media import mean_interval, t_cdf
from app.stats.sizing import blocco_di_ogni_data, independent_blocks

MODELLI = ("dopo_movimento", "stagionalita", "evento")
MESI = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")
GIORNI = ("lun", "mar", "mer", "gio", "ven")


@dataclass(frozen=True)
class Serie:
    date: list[date]
    chiusure: list[float]


def _percentile(ordinati: list[float], q: float) -> float:
    """Interpolazione lineare fra i due ranghi vicini (la definizione di numpy)."""
    pos = q * (len(ordinati) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordinati) - 1)
    return ordinati[lo] + (ordinati[hi] - ordinati[lo]) * (pos - lo)


def _misura(valori: list[float], date_: list[date], orizzonte: int) -> dict:
    """Media, mediana, quota positiva, finestre indipendenti, intervallo e la
    FORMA della distribuzione (ondata 1, F1): con venti casi la media da sola
    inganna — NVDA attorno alle trimestrali, media +0,6% e mediana −3,6%."""
    if not valori:
        return {"casi": 0, "finestre": 0, "media": None, "mediana": None,
                "quota_positivi": None, "intervallo": None,
                "p10": None, "p90": None, "peggiore": None, "migliore": None}
    finestre = independent_blocks(date_, orizzonte)
    iv = mean_interval(valori, effective_n=finestre)
    ordinati = sorted(valori)
    return {
        "casi": len(valori), "finestre": finestre,
        "media": mean(valori), "mediana": median(valori),
        "quota_positivi": sum(1 for v in valori if v > 0) / len(valori),
        "intervallo": list(iv) if iv else None,
        "p10": _percentile(ordinati, 0.10), "p90": _percentile(ordinati, 0.90),
        "peggiore": ordinati[0], "migliore": ordinati[-1],
    }


#: Quanti casi al massimo nell'elenco (FA-193): i piu' recenti. Il conteggio e
#: il verdetto usano sempre tutti.
MAX_CASI = 500


def elenco_casi(date_: list[date], valori: list[float], orizzonte: int,
                mosse: list[float] | None = None) -> list[dict]:
    """I casi uno per uno, dal piu' recente (FA-193): data, esito, episodio
    (la finestra indipendente a cui appartiene, numerata in ordine di tempo
    da 1) e se e' il primo giorno del suo episodio. `mosse`, se c'e', e' la
    variazione che ha fatto scattare la condizione."""
    if not valori:
        return []
    blocchi = blocco_di_ogni_data(date_, orizzonte)
    visti: set[int] = set()
    righe = []
    for i in sorted(range(len(date_)), key=lambda k: date_[k]):
        b = blocchi[i]
        righe.append({"data": date_[i].isoformat(), "esito": valori[i], "episodio": b + 1,
                      "primo": b not in visti, **({"mossa": mosse[i]} if mosse is not None else {})})
        visti.add(b)
    return list(reversed(righe))[:MAX_CASI]


def _quantili(valori: list[float]) -> dict:
    o = sorted(valori)
    return {"media": mean(o), "mediana": median(o), "p10": _percentile(o, 0.10), "p90": _percentile(o, 0.90)}


def percorso_cumulato(chiusure: list[float], partenze: list[int], orizzonte: int,
                      base: list[int] | None = None) -> list[dict]:
    """FA-194: il rendimento cumulato seduta per seduta, da 0 a `orizzonte`,
    per i casi che partono dagli indici `partenze`: media, mediana, 10° e 90°
    percentile; e la media della base sugli indici `base`."""
    if not partenze:
        return []
    out = []
    for k in range(orizzonte + 1):
        v = [chiusure[t + k] / chiusure[t] - 1.0 for t in partenze]
        riga = {"seduta": k, **_quantili(v)}
        if base:
            vb = [chiusure[t + k] / chiusure[t] - 1.0 for t in base]
            riga["base"] = mean(vb)
        out.append(riga)
    return out


def escursioni(chiusure: list[float], partenze: list[int], orizzonte: int) -> dict | None:
    """FA-194: per ogni caso la discesa massima (MAE, <= 0) e la salita
    massima (MFE, >= 0) LUNGO il percorso, riassunte. Dice quanto bisognava
    sopportare per arrivare all'esito, cioe' la geometria di uno stop."""
    if not partenze:
        return None
    mae, mfe = [], []
    for t in partenze:
        tratto = [chiusure[t + k] / chiusure[t] - 1.0 for k in range(1, orizzonte + 1)]
        mae.append(min(0.0, min(tratto)))
        mfe.append(max(0.0, max(tratto)))
    om, of = sorted(mae), sorted(mfe)
    return {"mae_mediana": median(om), "mae_p10": _percentile(om, 0.10),
            "mfe_mediana": median(of), "mfe_p90": _percentile(of, 0.90), "casi": len(partenze)}


def istogramma(cond: list[float], base: list[float], fasce: int = 12) -> list[dict]:
    """La quota dei casi per fascia, per la condizione e per la base sulla
    STESSA griglia, cosi' le due forme si confrontano a occhio. La griglia va
    dal 2° al 98° percentile dell'unione: le code estreme finiscono nelle
    fasce di bordo invece di schiacciare tutto il resto."""
    if not cond or not base:
        return []
    tutti = sorted(cond + base)
    lo, hi = _percentile(tutti, 0.02), _percentile(tutti, 0.98)
    if hi <= lo:
        return []
    passo = (hi - lo) / fasce

    def quote(valori: list[float]) -> list[float]:
        n = [0] * fasce
        for v in valori:
            i = min(fasce - 1, max(0, int((v - lo) / passo)))
            n[i] += 1
        return [c / len(valori) for c in n]

    qc, qb = quote(cond), quote(base)
    return [{"da": lo + i * passo, "a": lo + (i + 1) * passo, "condizione": qc[i], "base": qb[i]}
            for i in range(fasce)]


def stabilita(cond: list[float], date_cond: list[date], base: list[float], date_base: list[date]) -> dict:
    """La differenza dalla base nella prima e nella seconda meta' della storia
    (ondata 1, F4). Il progetto si fida di un effetto solo se regge su
    campioni disgiunti: un risultato che cambia segno fra le due meta' e'
    rumore anche quando l'intervallo complessivo esclude lo zero."""
    if not date_base:
        return {"prima": None, "seconda": None, "concordi": False}
    taglio = date_base[len(date_base) // 2]

    def diff(prima: bool) -> float | None:
        c = [v for v, g in zip(cond, date_cond, strict=True) if (g < taglio) == prima]
        b = [v for v, g in zip(base, date_base, strict=True) if (g < taglio) == prima]
        return mean(c) - mean(b) if c and b else None

    a, z = diff(True), diff(False)
    return {"prima": a, "seconda": z, "taglio": taglio.isoformat(),
            "concordi": a is not None and z is not None and (a > 0) == (z > 0)}


def p_valore(valori: list[float], finestre: int) -> float | None:
    """La t della media contro zero, con le finestre indipendenti come gradi
    di liberta' (la stessa convenzione di `mean_interval`)."""
    n = len(valori)
    if n < 2 or finestre < 2:
        return None
    m = mean(valori)
    sd = (sum((v - m) ** 2 for v in valori) / (n - 1)) ** 0.5
    if sd == 0:
        return None
    t = m / (sd / finestre ** 0.5)
    return 2.0 * (1.0 - t_cdf(abs(t), finestre - 1))


def benjamini_hochberg(pvals: list[float | None], q: float = 0.05) -> list[bool]:
    """Quali confronti sopravvivono alla correzione per famiglia (ondata 1, F5).
    I None (non stimabili) contano nella famiglia e non sopravvivono mai."""
    m = len(pvals)
    validi = sorted((p, i) for i, p in enumerate(pvals) if p is not None)
    soglia_k = 0
    for k, (p, _) in enumerate(validi, start=1):
        if p <= q * k / m:
            soglia_k = k
    passano = {i for _, i in validi[:soglia_k]}
    return [i in passano for i in range(m)]


MIN_FINESTRE = 20


def confronto(cond: dict, base: dict, stab: dict | None = None) -> dict:
    """La differenza dalla base col suo intervallo e un verdetto (D-84).

    L'intervallo somma in quadratura le due semi-ampiezze: tratta i due
    campioni come indipendenti, mentre la base contiene anche i casi della
    condizione, quindi e' un'approssimazione (leggermente larga quando la
    condizione e' rara, che e' il caso comune). Il verdetto ha tre stati e
    mai «conviene»: lo Studio descrive.
    """
    m, b = cond.get("media"), base.get("media")
    if m is None or b is None:
        return {"differenza": None, "intervallo_differenza": None, "verdetto": "non_concludente"}
    diff = m - b
    ic, ib = cond.get("intervallo"), base.get("intervallo")
    intervallo = None
    if ic and ib:
        semi = (((ic[1] - ic[0]) / 2) ** 2 + ((ib[1] - ib[0]) / 2) ** 2) ** 0.5
        intervallo = [diff - semi, diff + semi]
    if cond.get("finestre", 0) < MIN_FINESTRE or intervallo is None:
        verdetto = "non_concludente"
    elif intervallo[0] <= 0 <= intervallo[1]:
        verdetto = "compatibile_con_zero"
    elif stab is not None and not stab.get("concordi"):
        # Esclude lo zero nel complesso ma cambia segno fra le due meta'.
        verdetto = "instabile"
    else:
        verdetto = "diversa_dalla_base"
    return {"differenza": diff, "intervallo_differenza": intervallo, "verdetto": verdetto}


def dopo_movimento(s: Serie, *, sedute: int, soglia_pct: float, orizzonte: int) -> dict:
    """Le H sedute dopo ogni giorno in cui la variazione delle N sedute
    precedenti e' stata almeno `soglia_pct` (negativa = un calo almeno pari)."""
    c, d = s.chiusure, s.date
    soglia = soglia_pct / 100.0
    casi, date_casi, base, date_base = [], [], [], []
    mosse, partenze, partenze_base = [], [], []
    for t in range(sedute, len(c) - orizzonte):
        if c[t] <= 0 or c[t - sedute] <= 0:
            continue
        avanti = c[t + orizzonte] / c[t] - 1.0
        base.append(avanti)
        date_base.append(d[t])
        partenze_base.append(t)
        mossa = c[t] / c[t - sedute] - 1.0
        if (soglia < 0 and mossa <= soglia) or (soglia > 0 and mossa >= soglia):
            casi.append(avanti)
            date_casi.append(d[t])
            mosse.append(mossa)
            partenze.append(t)
    out = {"condizione": _misura(casi, date_casi, orizzonte),
           "base": _misura(base, date_base, orizzonte),
           "parametri": {"sedute": sedute, "soglia_pct": soglia_pct, "orizzonte": orizzonte}}
    stab = stabilita(casi, date_casi, base, date_base)
    out.update(confronto(out["condizione"], out["base"], stab))
    out["stabilita"] = stab
    out["istogramma"] = istogramma(casi, base)
    out["elenco_casi"] = elenco_casi(date_casi, casi, orizzonte, mosse)
    # La base del percorso: un campione regolare delle finestre (al massimo
    # ~400), che per una media basta e tiene il calcolo sotto i millisecondi.
    passo = max(1, len(partenze_base) // 400)
    out["percorso"] = percorso_cumulato(c, partenze, orizzonte, partenze_base[::passo])
    out["escursioni"] = escursioni(c, partenze, orizzonte)
    return out


def stagionalita(s: Serie) -> dict:
    """Rendimento per mese (da fine mese a fine mese) e per giorno della
    settimana (seduta su seduta). Mesi e giorni diversi sono finestre
    disgiunte: ogni osservazione e' indipendente dalle altre del suo gruppo."""
    # FA-195: i mesi dal proprietario unico (`app/stats/calendario`), lo
    # stesso numero del calendario della pagina Mercati. Prima si accoppiavano
    # mesi consecutivi NELL'ELENCO: un mese senza sedute dava un rendimento di
    # due mesi attribuito al secondo.
    mensili = cal.rendimenti_mensili(s.date, s.chiusure)
    per_mese: dict[int, list[float]] = defaultdict(list)
    tutti_mesi = []
    for (_a, m), r in sorted(mensili.items()):
        per_mese[m].append(r)
        tutti_mesi.append(r)
    per_giorno: dict[int, list[float]] = defaultdict(list)
    tutti_giorni = []
    for i in range(1, len(s.chiusure)):
        if s.chiusure[i - 1] > 0 and s.date[i].weekday() < 5:
            r = s.chiusure[i] / s.chiusure[i - 1] - 1.0
            per_giorno[s.date[i].weekday()].append(r)
            tutti_giorni.append(r)

    def gruppo(valori: list[float]) -> dict:
        iv = mean_interval(valori, effective_n=len(valori)) if valori else None
        # FA-192: la mediana mancava e la tabella stampava «—» su tutte le
        # diciassette righe, proprio la misura che l'ondata 1 ha messo accanto
        # alla media perche' la media da sola inganna.
        return {"casi": len(valori), "finestre": len(valori),
                "media": mean(valori) if valori else None,
                "mediana": median(valori) if valori else None,
                "quota_positivi": sum(1 for v in valori if v > 0) / len(valori) if valori else None,
                "intervallo": list(iv) if iv else None}

    mesi = [{"mese": MESI[m - 1], **gruppo(per_mese.get(m, []))} for m in range(1, 13)]
    giorni = [{"giorno": GIORNI[g], **gruppo(per_giorno.get(g, []))} for g in range(5)]
    # F5: diciassette confronti contro lo zero sono una famiglia. Senza la
    # correzione su ^GSPC quattro mesi «uscivano», circa uno per pura
    # combinatoria. `significativo` e' cio' che sopravvive a Benjamini-Hochberg.
    pv = [p_valore(per_mese.get(m, []), len(per_mese.get(m, []))) for m in range(1, 13)] + [
        p_valore(per_giorno.get(g, []), len(per_giorno.get(g, []))) for g in range(5)]
    passano = benjamini_hochberg(pv)
    for i, riga in enumerate(mesi + giorni):
        riga["significativo"] = passano[i]
    return {
        "mesi": mesi,
        "base_mesi": gruppo(tutti_mesi),
        "giorni": giorni,
        "base_giorni": gruppo(tutti_giorni),
        "confronti": len(pv),
        "sopravvissuti": sum(passano),
        # FA-195: anni per mesi, per vedere se un mese «forte» lo e' con
        # regolarita' o per tre anni eccezionali.
        "calendario": cal.calendario_mensile(s.date, s.chiusure),
    }


PRIMA, DOPO = 5, 10


def evento(s: Serie, date_eventi: list[date], *, orizzonte: int = 5) -> dict:
    """Il percorso medio da PRIMA sedute prima a DOPO sedute dopo ogni evento,
    in rendimento dalla chiusura della seduta precedente all'evento; e la
    misura a `orizzonte` sedute contro il caso base."""
    c = s.chiusure
    percorsi, a_h, date_h, date_ev = [], [], [], []
    for g in sorted(set(date_eventi)):
        # La seduta dell'evento: la prima in data g o dopo (un annuncio di
        # sabato reagisce il lunedi').
        t0 = _primo_da(s.date, g)
        if t0 - 1 - PRIMA < 0 or t0 + DOPO >= len(c) or c[t0 - 1] <= 0:
            continue
        rif = c[t0 - 1]
        percorsi.append([c[t0 + k] / rif - 1.0 for k in range(-PRIMA - 1, DOPO + 1)])
        a_h.append(c[t0 - 1 + orizzonte] / rif - 1.0)
        date_h.append(g)
        date_ev.append(s.date[t0])
    base, date_base = [], []
    for t in range(1, len(c) - orizzonte):
        if c[t - 1] > 0:
            base.append(c[t - 1 + orizzonte] / c[t - 1] - 1.0)
            date_base.append(s.date[t])
    # FA-194: per ogni seduta anche mediana, 10° e 90° percentile e quanti
    # eventi contribuiscono (tutti, qui: i bordi sono gia' esclusi sopra).
    percorso = [
        {"seduta": k, "n": len(percorsi), **_quantili([p[k + PRIMA + 1] for p in percorsi])}
        for k in range(-PRIMA - 1, DOPO + 1)
    ] if percorsi else []
    # I percorsi dei singoli eventi, se pochi: con venti eventi la media
    # nasconde proprio cio' che si vuole vedere (due code che la trascinano).
    singoli = [{"data": g.isoformat(), "valori": p} for g, p in zip(date_ev, percorsi, strict=True)] \
        if 0 < len(percorsi) <= 40 else []
    a_orizzonte = _misura(a_h, date_h, orizzonte)
    base_m = _misura(base, date_base, orizzonte)
    stab = stabilita(a_h, date_h, base, date_base)
    return {"percorso": percorso, "singoli": singoli, "a_orizzonte": a_orizzonte, "base": base_m,
            "orizzonte": orizzonte, **confronto(a_orizzonte, base_m, stab), "stabilita": stab,
            "istogramma": istogramma(a_h, base), "elenco_casi": elenco_casi(date_h, a_h, orizzonte)}


def _primo_da(date_: list[date], g: date) -> int:
    lo, hi = 0, len(date_)
    while lo < hi:
        m = (lo + hi) // 2
        if date_[m] < g:
            lo = m + 1
        else:
            hi = m
    return lo


# ─── Le fonti ──────────────────────────────────────────────────────────────

#: simbolo di mercato -> (giorno, serie). Piccolo per costruzione: i mercati
#: sono una ventina.
_SERIE_MERCATI: dict[str, tuple[date, Serie]] = {}


def serie_di(db: Session, simbolo: str) -> Serie | None:
    """Le chiusure del simbolo: dal catalogo per un titolo, dal dettaglio
    mercati per un indice o una materia prima."""
    from app.models import OhlcvDaily, Stock  # noqa: PLC0415

    t = simbolo.strip().upper()
    s = db.execute(select(Stock).where(Stock.ticker == t).limit(1)).scalars().first()
    if s is not None:
        righe = db.execute(select(OhlcvDaily.date, OhlcvDaily.close)
                           .where(OhlcvDaily.stock_id == s.id).order_by(OhlcvDaily.date)).all()
        d = [g if isinstance(g, date) else date.fromisoformat(str(g)[:10]) for g, _ in righe]
        return Serie(d, [float(c) for _, c in righe]) if righe else None
    # F20: la serie di un mercato passa dal dettaglio completo (indicatori
    # compresi): 3,5 s a freddo per la stagionalita' di ^GSPC. Vale per il
    # giorno, quindi si tiene per il giorno.
    oggi = date.today()
    in_cache = _SERIE_MERCATI.get(t)
    if in_cache is not None and in_cache[0] == oggi:
        return in_cache[1]
    from app.services import rischio_posizioni_service as rp  # noqa: PLC0415

    barre = rp._barre_indice(t)
    if not barre:
        return None
    serie = Serie([date.fromisoformat(b.data[:10]) for b in barre], [b.chiusura for b in barre])
    _SERIE_MERCATI[t] = (oggi, serie)
    return serie


def date_trimestrali(simbolo: str) -> list[date]:
    from app.services import stock_fundamentals_service as sfs  # noqa: PLC0415

    f = sfs._CACHE.get(simbolo.strip().upper())
    out = []
    for e in (f.earnings if f is not None else []):
        if e.eps_reported is None:
            continue
        try:
            out.append(date.fromisoformat(str(e.date)[:10]))
        except ValueError:
            continue
    return out


def date_macro(db: Session, serie: str) -> list[date]:
    from app.models import MacroReleaseDate, MacroSeries  # noqa: PLC0415

    return list(db.execute(
        select(MacroReleaseDate.date).join(MacroSeries, MacroSeries.id == MacroReleaseDate.series_id)
        .where(MacroSeries.fred_series_id == serie).order_by(MacroReleaseDate.date)
    ).scalars())
