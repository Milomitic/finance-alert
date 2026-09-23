"""Gli esiti di piano, un segnale per riga.

⚠️ Il magazzino aggregato per detector sta in `platform.PlanPerfRowOut` e
risponde a «quale detector paga»; questo risponde a «che cosa e' successo a
QUESTO segnale». Le due viste leggono la stessa tabella e non vanno fuse: la
prima e' una classifica, la seconda un registro.
"""
from datetime import date

from pydantic import BaseModel


class PlanOutcomeRowOut(BaseModel):
    """La gara stop-contro-target di un singolo segnale.

    ⚠️ Le tre date delle gambe escono GREZZE, senza nessun «stop troppo
    stretto» precalcolato: l'ordine si deduce, e una conclusione congelata qui
    vivrebbe in due posti il giorno che qualcuno la affina.
    """

    alert_id: int
    ticker: str
    name: str | None = None
    detector: str
    tone: str
    signal_date: date
    #: La barra da cui parte la gara: la PRIMA EMISSIONE dell'alert, non
    #: l'ultima revisione. Puo' essere posteriore a `signal_date` di qualche
    #: seduta — e' la cadenza della scansione, e si vede.
    entry_date: date
    entry: float
    stop: float
    tp1: float
    tp2: float | None = None
    #: La distanza di rischio in prezzo: 1R, il denominatore di tutto il resto.
    r: float
    horizon_days: int

    #: tp1 | stop | ambigua | scaduto. ⚠️ `ambigua` = stop e target nella
    #: stessa barra: il dato giornaliero non dice quale sia venuto prima, si
    #: assegna lo stop (pessimista) e la categoria resta a se' per poter
    #: misurare dopo quanto costa quella convenzione.
    esito: str
    resolved_date: date
    bars_to_outcome: int
    r_multiple: float
    mae_r: float
    mfe_r: float
    tp2_reached: bool

    #: Primo tocco di ciascuna gamba NELL'ORIZZONTE, a prescindere da chi ha
    #: vinto — anche dopo la chiusura della posizione. «Stop il giorno 3,
    #: target il giorno 12» rende -1R ed e' giusto, e dice anche che quello
    #: stop era troppo stretto: un fatto che l'esito da solo non porta.
    stop_hit_date: date | None = None
    tp1_hit_date: date | None = None
    tp2_hit_date: date | None = None


class PlanOutcomeSummaryOut(BaseModel):
    """Il riassunto della popolazione FILTRATA, mai della pagina."""

    n: int
    #: Le finestre INDIPENDENTI. Righe le cui finestre si sovrappongono non
    #: sono estrazioni indipendenti, e l'intervallo lo paga.
    effective_n: int
    horizon_days: int
    #: L'intestazione: l'attesa in R. ⚠️ NON il tasso di successo — TP1 sta a
    #: R:R fino a 4,0, quindi un tasso letto da solo sembrerebbe pessimo
    #: mentre il sistema guadagna.
    expectancy_r: float
    expectancy_ci: list[float] | None = None
    verdict: str
    win_rate: float
    esiti: dict[str, int]
    stop_too_tight: int
    mae_r_on_wins: float | None = None
    mfe_r_on_losses: float | None = None
    median_bars: float | None = None
    low_confidence: bool
    #: Le righe filtrate escluse dalle misure perche' a finestra ancora aperta.
    open_excluded: int = 0


class PlanOutcomeListOut(BaseModel):
    items: list[PlanOutcomeRowOut]
    total: int
    has_more: bool
    counts_by_detector: dict[str, int]
    #: `None` quando il filtro non seleziona niente: zero righe non hanno
    #: un'attesa, e stampare 0,00 R sarebbe un'affermazione invece di
    #: un'assenza.
    summary: PlanOutcomeSummaryOut | None = None
    #: Quante righe dell'elenco sono a finestra aperta, e quindi fuori dal
    #: riassunto. Fuori da `summary` perche' serve anche quando il riassunto
    #: manca: sole finestre aperte si dice «in corso», non «vuoto».
    open_excluded: int = 0
