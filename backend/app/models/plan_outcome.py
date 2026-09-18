"""Il magazzino degli esiti di PIANO: la gara fra stop e target, persistita.

Accanto a `signal_outcomes`, non dentro, e la ragione e' temporale prima che
concettuale.

Una riga di `signal_outcomes` nasce solo quando l'orizzonte fisso del detector
e' trascorso — per `analyst_momentum` sono 63 sedute, cioe' circa tre mesi.
Un esito di piano si risolve quando stop o target vengono toccati, di regola
molto prima: sul caso che ha fatto nascere questo lavoro (FLNC, alert 18987)
il target e' stato colpito dopo dodici sedute mentre l'etichetta a orizzonte
fisso non arrivera' prima di fine novembre. Appendere queste colonne a
`signal_outcomes` le farebbe aspettare l'orizzonte, cioe' riprodurrebbe
esattamente il difetto che questa tabella esiste per chiudere.

⚠️ E le due tabelle rispondono a domande diverse, che non vanno mescolate:

    signal_outcomes   il detector prevede la deriva a orizzonte fisso?
    plan_outcomes     il piano mostrato a schermo avrebbe pagato?

Calibrazione, monitor di deriva, cubo dei detector e curva di equity sono
tutti costruiti sulla prima. Ridefinirla cambierebbe in silenzio il
significato di ogni numero d'efficacia gia' a schermo.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

#: Il livello di invalidazione l'ha EMESSO il detector al momento dello scatto.
FONTE_EMESSO = "emesso"
#: Il livello e' stato RICOSTRUITO all'indietro da dati storici esatti (la
#: chiusura precedente di un gap, i pivot nella catena dello snapshot). ⚠️ Va
#: tenuto distinguibile per sempre: un'analisi deve poter escludere le righe
#: ricostruite con un WHERE, perche' una ricostruzione sbagliata e' del tutto
#: indistinguibile da una giusta finche' nessuno guarda questo campo.
FONTE_RICOSTRUITO = "ricostruito"


class PlanOutcome(Base):
    """L'esito della gara stop-contro-target per UN alert."""

    __tablename__ = "plan_outcomes"
    __table_args__ = (
        # ⚠️ Un esito per alert, imposto dal DATABASE e non dalla diligenza del
        # chiamante: la maturazione gira a ogni scansione, e un controllo
        # «esiste gia'?» in Python ha una finestra di corsa. Righe doppie
        # conterebbero due volte lo stesso trade, cioe' dichiarerebbero un
        # campione piu' grande di quello che c'e' — il difetto che questo
        # progetto sorveglia piu' di ogni altro.
        SAIndex("ix_plan_outcomes_alert", "alert_id", unique=True),
        SAIndex("ix_plan_outcomes_detector", "detector"),
        SAIndex("ix_plan_outcomes_signal_date", "signal_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[int] = mapped_column(Integer, nullable=False)
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    tone: Mapped[str] = mapped_column(String(8), nullable=False)  # bull | bear
    #: L'orizzonte oltre il quale la gara non guarda piu'. E' lo STESSO numero
    #: che usa `signal_outcomes`, cosi' le due etichette coprono la stessa
    #: finestra e restano confrontabili.
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── La geometria, CONGELATA ────────────────────────────────────────────
    # Sarebbe ricalcolabile dallo snapshot, e si scrive lo stesso: e' tarata
    # (le tabelle per orizzonte, il tetto a 8 ATR, il pavimento a floor*ATR) e
    # quelle costanti cambieranno. Una riga che rimandasse al calcolo verrebbe
    # riletta domani con una geometria diversa da quella che ha prodotto
    # l'esito, e il magazzino direbbe cose che non sono mai successe.
    #
    #: La barra da cui parte la gara: quella della PRIMA EMISSIONE dell'alert,
    #: non del segnale e non dell'ultima revisione.
    #:
    #: E' il primo momento in cui si sarebbe potuto agire davvero. Fra la barra
    #: del segnale e la prima emissione passa la cadenza della scansione
    #: (mediana ZERO giorni, 82% entro un giorno, misurato in produzione), e
    #: attribuire al piano un movimento avvenuto prima che l'alert esistesse lo
    #: farebbe sembrare migliore di quanto sia.
    #:
    #: ⚠️ E NON `triggered_at`, che sembra questo campo e non lo e'. Un alert e'
    #: una riga VIVA: finche' il segnale persiste ogni scansione lo rivede e
    #: riscrive sia `triggered_at` sia `trigger_price`. Misurato il 2026-09-18
    #: su 8.736 alert: 80% ha almeno una revisione, 73% ha una prima emissione
    #: anteriore a `triggered_at`, uno ne conta 103, e nel 18% dei casi il
    #: prezzo mostrato dista oltre il 2% dalla chiusura della barra del
    #: segnale. Ancorare li' renderebbe l'esito dipendente da QUANDO gira la
    #: maturazione — un magazzino che cambia con l'ora in cui lo si guarda.
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop: Mapped[float] = mapped_column(Float, nullable=False)
    tp1: Mapped[float] = mapped_column(Float, nullable=False)
    tp2: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: La distanza di rischio in prezzo: 1R. Denominatore di tutto il resto.
    r: Mapped[float] = mapped_column(Float, nullable=False)

    # ── L'esito ────────────────────────────────────────────────────────────
    #: tp1 | stop | ambigua | scaduto — vedi `plan_outcome_service.ESITI`.
    #: ⚠️ `ambigua` (stop e target nella stessa barra) e' una categoria a se' e
    #: non va fusa con `stop`, benche' valga -1R: tenerla separata e' l'unico
    #: modo per misurare DOPO quanto costa la convenzione pessimista.
    esito: Mapped[str] = mapped_column(String(16), nullable=False)
    resolved_date: Mapped[date] = mapped_column(Date, nullable=False)
    bars_to_outcome: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Il guadagno in multipli di R. ⚠️ NON e' una costante per detector: i
    #: target sono tagliati a un multiplo di ATR, quindi l'R di un TP1 varia
    #: per segnale — misurato sui vettori d'oro, da 0,2 a 4,0. E' la ragione
    #: per cui va registrato trade per trade invece che dedotto.
    r_multiple: Mapped[float] = mapped_column(Float, nullable=False)
    #: Massima escursione avversa e favorevole, in R, fino alla barra che
    #: risolve. Continue, quindi con molta piu' potenza statistica di un
    #: binario per osservazione: sono gli ingressi diretti per tarare stop
    #: (MAE sui vinti) e target (MFE sui persi e sui non risolti).
    mae_r: Mapped[float] = mapped_column(Float, nullable=False)
    mfe_r: Mapped[float] = mapped_column(Float, nullable=False)
    #: Il secondo target e' stato toccato MENTRE LA POSIZIONE ERA APERTA.
    #: Tenuto fuori dall'esito primario perche' mescolarlo renderebbe
    #: incomparabili le righe.
    tp2_reached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── L'ORDINE degli eventi ──────────────────────────────────────────────
    # La data di PRIMO TOCCO di ciascuna gamba nell'orizzonte, a prescindere da
    # chi ha vinto — anche quella toccata DOPO la chiusura della posizione.
    #
    # ⚠️ Rispondono a una domanda diversa dall'esito, e senza di loro quella
    # domanda non e' ponibile. «Stop il giorno 3, target il giorno 12» rende
    # -1R ed e' giusto, perche' la posizione era chiusa; ma dice anche che
    # quello stop era troppo stretto e il trade aveva ragione. Quel fatto non
    # e' ricavabile dall'esito, e nemmeno da MAE/MFE, che si fermano alla
    # risoluzione proprio perche' misurano il TRADE e non la TARATURA.
    #
    # Da queste tre l'ordine si deduce, «entrambe toccate» si deduce, e nessuna
    # aggregazione e' congelata nello schema.
    stop_hit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tp1_hit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tp2_hit_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ── Provenienza ────────────────────────────────────────────────────────
    source: Mapped[str] = mapped_column(String(16), nullable=False,
                                        default=FONTE_EMESSO)
    #: Con quale versione della regola questa riga e' stata etichettata. Senza,
    #: una modifica al metodo mescolerebbe in silenzio le popolazioni di prima
    #: e di dopo — la stessa ragione per cui esiste `OUTCOME_METHOD_VERSION`.
    method_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    matured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
