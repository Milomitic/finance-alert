"""Geometria del piano di trade — gemella Python di `lib/tradePlaybook.ts`.

Serve a far correre stop e target sulle barre (esito basato sul piano). Il TS
resta cio' che l'utente VEDE; questo modulo deve rendere gli stessi numeri, e
`frontend/src/lib/playbookVectors.json` e' il ponte che lo pretende da
entrambi i lati.

⚠️ Modulo FOGLIA, senza una sola dipendenza oltre alla libreria standard, e
non e' pignoleria. La fonte unica dei periodi degli indicatori viveva dentro
un servizio che importava SQLAlchemy e loguru: chi ne aveva bisogno non poteva
importarla senza tirarsi dietro mezzo stack, quindi nessuno la importava e
quattordici chiamate riscrivevano i numeri a mano. Una fonte unica che nessuno
puo' consumare e' una fonte unica solo nel commento.

Cosa NON e' portato, di proposito: `riskBudgetPct`, `positionPct`, `leverage`
e la nota di leva. Sono propensione al rischio e resa a schermo, non
geometria, e per far correre una gara fra stop e target non servono.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Geometria per orizzonte, identica al TS: `floor`/`tp*Cap` sono multipli di
# ATR, `tp*R` sono multipli di R. Medio e lungo: VALIDATI da backtest
# (2026-05-25) e confermati dallo studio del 2026-09-23, dove nessuna delle 73
# alternative li batte fuori campione.
#
# ⚠️ Il BREVE e' cambiato il 2026-09-24 (PLAN_METHOD_VERSION "4"). Il
# pavimento a 0,5 ATR dava uno stop mediano dell'1,7%: ~0,05 R a operazione
# solo di costi, e il piano rendeva MENO dello stesso piano su un titolo a
# caso. Pavimento 4 ATR e TP1 a 1,5 R, senza tetto in ATR che morda (lo stop
# e' gia' tagliato a 8 ATR, quindi 1,5 R <= 12 ATR): e' l'ipotesi scritta in
# `preregistrazione.json` PRIMA di guardare 274 titoli mai usati, e su quelli
# confermata (netto a costo 0,1%: -0,055 -> -0,014 R, t 3,50). Non e' un
# vantaggio trovato, e' un danno tolto: a costo zero il netto non cambia.
# `docs/superpowers/specs/2026-09-23-studio-taratura-e-ml-findings.md` §4.
# TP2 non e' mai stato messo in gara (la gara e' TP1 contro stop): tiene il
# rapporto 1,5x col TP1 che aveva prima.
_HZ: dict[str, dict[str, float | str]] = {
    "short":  {"floor": 4.0, "tp1R": 1.5, "tp1Cap": 12.0, "tp2R": 2.25,
               "tp2Cap": 18.0, "label": "Breve"},
    "medium": {"floor": 2.5, "tp1R": 2.0, "tp1Cap": 10.0, "tp2R": 3.0,
               "tp2Cap": 18.0, "label": "Medio"},
    "long":   {"floor": 1.0, "tp1R": 3.0, "tp1Cap": 8.0, "tp2R": 4.5,
               "tp2Cap": 14.0, "label": "Lungo"},
}

# Limita la coda catastrofica (uno stop strutturale contro una EMA200 lontana
# puo' valere il 40%) a 8 ATR. Validato 2026-05-25 come neutro sull'attesa.
_STOP_CAP_ATR = 8.0

# Ripiego sull'orizzonte quando la catena sta in un giorno solo.
_PRIOR: dict[str, str] = {
    "high52_momentum": "long", "trend_pullback": "long", "structure_break": "long",
    "adx_confirmation": "long", "pead": "long", "analyst_momentum": "long",
    "insider_buy": "long",
    "sr_flip": "medium", "volume_breakout": "medium", "squeeze_expansion": "medium",
    "rsi_divergence": "medium", "macd_divergence": "medium",
    "hidden_divergence": "medium", "oversold_reversal": "medium",
    "chart_pattern": "medium",
    "candle_reversal": "short", "gap_and_go": "short",
}


@dataclass(frozen=True)
class Target:
    label: str
    price: float
    rr: float


@dataclass(frozen=True)
class PianoDiTrade:
    side: str          # "long" | "short"
    horizon: str       # l'ETICHETTA: "Breve" | "Medio" | "Lungo"
    entry: float
    stop: float
    stop_pct: float
    stop_capped: bool
    r: float           # la distanza di rischio in prezzo: 1R
    targets: list[Target]


#: I tre ingressi della geometria e il nome che portano una volta FISSATI alla
#: prima emissione.
#:
#: ⚠️ L'ingresso era gia' fissato (`snapshot.first_price`), questi no: `atr`,
#: `invalidation` e `horizon` vengono sostituiti a OGNI revisione insieme al
#: resto dello snapshot, e un alert su cinque non ne ha nemmeno una. Il piano
#: leggeva quindi un prezzo di un giorno e una volatilita' di un altro.
#:
#: Misurato in produzione il 2026-09-22 su MRNA (alert 18192, rottura di
#: struttura del 12 agosto a 63,67): il 19 agosto il titolo ha fatto +177% in
#: una seduta, l'alert e' rimasto vivo fino al 21 e l'ATR e' passato da 3,96 a
#: 14,89. Lo stop del piano finiva a 26,46 — il 58% sotto un ingresso che
#: nessuno avrebbe piu' potuto prendere — e i due target collassavano
#: entrambi sul tetto del +95%. Con l'ATR del 12 agosto: stop 53,76, target
#: 83,48 e 93,39, entrambi toccati dal gap del 19. Su 7.296 alert rivisti,
#: 296 hanno uno scarto di ATR oltre il 25% e 37 oltre il doppio.
#:
#: Il vincolo non e' «l'ATR non deve muoversi»: e' che TUTTI gli ingressi del
#: piano vengano dallo stesso istante di quello d'ingresso. Il resto dello
#: snapshot — Forza, catena, regime — continua a descrivere l'analisi di
#: adesso, ed e' giusto cosi': quello che mancava era la separazione fra le
#: due letture, non il congelamento di entrambe.
_CONGELATI: dict[str, str] = {
    "atr": "first_atr",
    "invalidation": "first_invalidation",
    "horizon": "first_horizon",
}


#: I nomi dei campi fissati, per chi li SCRIVE (lo scan) e per chi li riempie
#: all'indietro (`app.scripts.backfill_plan_inputs`). Un elenco copiato si
#: dimentica del campo successivo che si aggiunge, e il difetto sarebbe di
#: nuovo un piano che mescola due istanti.
INGRESSI_CONGELATI: tuple[str, ...] = tuple(_CONGELATI.values())


def ingressi_del_piano(snapshot: dict) -> dict:
    """ATR, invalidazione e orizzonte con cui il piano si costruisce.

    Quelli della PRIMA EMISSIONE quando ci sono, coi correnti come ripiego
    DICHIARATO per gli alert che precedono i campi: il meglio disponibile, non
    una stima. Gemella di `ingressiDelPiano` in `lib/tradePlaybook.ts`.
    """
    return {
        vivo: (snapshot.get(congelato)
               if snapshot.get(congelato) is not None
               else snapshot.get(vivo))
        for vivo, congelato in _CONGELATI.items()
    }


def _numero(v: object) -> float | None:
    """Un numero vero e finito, o None. `bool` e' escluso perche' in Python e'
    un `int` e `True` passerebbe per 1.0 — un livello di invalidazione pari a
    True non e' un livello."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _orizzonte_dalla_catena(name: str | None, chain: list | None) -> str:
    """Dalla durata della catena, col prior del detector come ripiego.

    <= 7 giorni -> breve, <= 35 -> medio, oltre -> lungo. Una catena
    incrocio-d'oro -> pullback lunga mesi finisce su «lungo»; un inglobamento
    sulla stessa barra su «breve».
    """
    giorni: set[date] = set()
    for c in chain or []:
        d = c.get("date") if isinstance(c, dict) else None
        if isinstance(d, str) and len(d) >= 10:
            try:
                giorni.add(date.fromisoformat(d[:10]))
            except ValueError:
                continue
    if len(giorni) >= 2:
        span = (max(giorni) - min(giorni)).days
        return "short" if span <= 7 else ("medium" if span <= 35 else "long")
    return _PRIOR.get(name or "", "medium")


def costruisci_piano(
    snapshot: dict, entry: object, name: str | None,
) -> PianoDiTrade | None:
    """Il piano per UN segnale, o None quando non c'e' un livello strutturale.

    Puro: deriva tutto dallo snapshot dell'alert e dal prezzo di scatto.

    Stop = invalidazione strutturale, PAVIMENTATA a floor*ATR e TAGLIATA a
    8*ATR. Target = multipli di R, tagliati a un movimento in ATR perche'
    restino raggiungibili.
    """
    tone = snapshot.get("tone")
    if tone not in ("bull", "bear"):
        return None
    prezzo = _numero(entry)
    if prezzo is None or prezzo <= 0:
        return None

    # Gli ingressi dell'ISTANTE D'INGRESSO, non quelli dell'ultima revisione.
    ing = ingressi_del_piano(snapshot)

    inval = ing.get("invalidation")
    livello = _numero(inval.get("level")) if isinstance(inval, dict) else None
    if livello is None or livello <= 0:
        return None

    side = "long" if tone == "bull" else "short"
    segno = 1.0 if side == "long" else -1.0

    # Ancora di volatilita'. Il ripiego al 2% del prezzo tiene uniformi tutte
    # le formule per gli alert storici senza ATR nello snapshot.
    atr_dichiarato = _numero(ing.get("atr"))
    atr = atr_dichiarato if atr_dichiarato and atr_dichiarato > 0 else prezzo * 0.02

    # L'orizzonte stampato dallo scan ha la precedenza; la classificazione
    # dalla catena vale per gli alert che lo precedono.
    # ⚠️ Un valore NON riconosciuto viene trattato come assente invece di
    # sollevare: il TS qui esploderebbe su `_HZ[hz]` e a schermo lo
    # raccoglierebbe l'ErrorBoundary, ma questo modulo gira in un ciclo su
    # migliaia di alert, dove un'eccezione fermerebbe la maturazione di tutti
    # gli altri. La divergenza riguarda solo dati gia' corrotti.
    # ⚠️ La catena resta quella VIVA: e' l'ultimo ripiego per gli alert che
    # precedono sia `first_horizon` sia `horizon`, e per quelli la catena
    # originale non esiste piu' da nessuna parte. Un ripiego dichiarato batte
    # un valore inventato.
    hz = ing.get("horizon")
    if hz not in _HZ:
        hz = _orizzonte_dalla_catena(name, snapshot.get("chain"))
    P = _HZ[hz]

    dist_strutturale = abs(prezzo - livello)
    r = min(max(dist_strutturale, float(P["floor"]) * atr), _STOP_CAP_ATR * atr)
    if r <= 0:
        return None
    # Il tetto morde: lo stop d'esecuzione e' PIU' STRETTO dell'invalidazione
    # strutturale, e chi legge il piano deve saperlo.
    stop_capped = dist_strutturale > _STOP_CAP_ATR * atr
    stop = prezzo - segno * r

    # I target non possono superare il ~100% (uno short non guadagna di piu').
    movimento_max = 0.95 * prezzo
    d1 = min(float(P["tp1R"]) * r, float(P["tp1Cap"]) * atr, movimento_max)
    d2 = min(float(P["tp2R"]) * r, float(P["tp2Cap"]) * atr, movimento_max)
    if d2 <= d1:
        d2 = min(d1 * 1.5, movimento_max)

    return PianoDiTrade(
        side=side,
        horizon=str(P["label"]),
        entry=prezzo,
        stop=stop,
        stop_pct=(r / prezzo) * 100.0,
        stop_capped=stop_capped,
        r=r,
        targets=[
            Target("Target 1", prezzo + segno * d1, d1 / r),
            Target("Target 2", prezzo + segno * d2, d2 / r),
        ],
    )
