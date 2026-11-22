"""Le operazioni dei fondi nell'ultimo trimestre, dalla piu' grande.

L'ordine e' il VALORE dell'operazione in dollari (richiesta dell'utente del
2026-11-22): quote comprate o vendute per il prezzo implicito nella
dichiarazione, il valore intero per una posizione nuova, quello della
dichiarazione precedente per un'uscita. Accanto resta lo spostamento del peso
nel portafoglio del fondo, che dice quanto contava la mossa per chi l'ha fatta.

Il peso prima viene dalla dichiarazione PRECEDENTE dello stesso fondo. Quando
la posizione non c'e' (Dataroma calcola da se' l'azione e a volte la riga
precedente manca) e l'azione e' un aumento o una riduzione, si ricava dal
cambio di quote: `peso / (1 + q/q)`. E' una stima che ignora il movimento del
prezzo nel trimestre, e si usa solo quando non c'e' altro.

⚠️ Solo fondi con una dichiarazione precedente: senza, «nuovo» non si puo'
distinguere da «tenuto da sempre» (la stessa regola di `_substantiated_new`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Float, and_, case, cast, func, select
from sqlalchemy.orm import Session, aliased

from app.models import Institutional, InstitutionalFiling, InstitutionalHolding, Stock
from app.services.institutional_service import _freshness_cutoff

AZIONI = ("new", "add", "reduce", "sold_out")


@dataclass
class Operazione:
    ticker: str
    company_name: str | None
    stock_id: int | None
    institutional_slug: str
    institutional_name: str
    action: str
    peso_prima: float
    peso_dopo: float
    delta_pp: float
    valore_operazione: int | None
    qoq_change_pct: float | None
    value_usd: int | None


@dataclass
class OperazioniTrimestre:
    trimestre: date | None
    fondi: int
    operazioni: list[Operazione]


def operazioni_ultimo_trimestre(
    db: Session, *, type_: str | None = None, limit: int = 30,
    azioni: tuple[str, ...] = AZIONI,
) -> OperazioniTrimestre:
    """Le operazioni del trimestre piu' recente, dalla piu' grande in dollari."""
    fresche = select(InstitutionalFiling.period_end_date).join(
        Institutional, Institutional.id == InstitutionalFiling.institutional_id,
    ).where(InstitutionalFiling.period_end_date >= _freshness_cutoff())
    if type_:
        fresche = fresche.where(Institutional.type == type_)
    trimestre = db.execute(select(func.max(fresche.subquery().c.period_end_date))).scalar()
    if trimestre is None:
        return OperazioniTrimestre(trimestre=None, fondi=0, operazioni=[])

    # La dichiarazione precedente di ogni fondo che ha depositato il trimestre.
    prec = (
        select(
            InstitutionalFiling.institutional_id.label("iid"),
            func.max(InstitutionalFiling.period_end_date).label("pp"),
        )
        .where(InstitutionalFiling.period_end_date < trimestre)
        .group_by(InstitutionalFiling.institutional_id)
        .subquery()
    )
    f_prec = aliased(InstitutionalFiling)
    # Pesi della dichiarazione precedente per (fondo, titolo); somma perche' un
    # 13F puo' portare piu' righe dello stesso titolo.
    pesi_prec = (
        select(
            f_prec.institutional_id.label("iid"),
            InstitutionalHolding.ticker.label("ticker"),
            func.sum(InstitutionalHolding.portfolio_pct).label("peso"),
            func.sum(InstitutionalHolding.value_usd).label("valore"),
        )
        .join(f_prec, f_prec.id == InstitutionalHolding.filing_id)
        .join(prec, and_(prec.c.iid == f_prec.institutional_id, prec.c.pp == f_prec.period_end_date))
        .group_by(f_prec.institutional_id, InstitutionalHolding.ticker)
        .subquery()
    )

    dopo = func.coalesce(InstitutionalHolding.portfolio_pct, 0.0)
    stima_prima = case(
        (
            and_(
                InstitutionalHolding.action.in_(("add", "reduce")),
                InstitutionalHolding.qoq_change_pct > -100.0,
            ),
            dopo / (1.0 + InstitutionalHolding.qoq_change_pct / 100.0),
        ),
        else_=0.0,
    )
    prima = func.coalesce(pesi_prec.c.peso, stima_prima)
    delta = (dopo - prima).label("delta")
    quote = InstitutionalHolding.shares
    valore = case(
        (InstitutionalHolding.action == "sold_out", pesi_prec.c.valore),
        (InstitutionalHolding.action == "new", InstitutionalHolding.value_usd),
        (
            and_(InstitutionalHolding.qoq_change_shares.is_not(None), quote > 0),
            # ⚠️ In decimale e DIVIDENDO prima: quote (fino a ~10^9) per valore
            # (fino a ~10^11) traboccano il bigint di Postgres. SQLite promuove
            # da solo e non lo vede (2026-11-22, 500 in produzione).
            cast(InstitutionalHolding.value_usd, Float) / cast(quote, Float)
            * func.abs(cast(InstitutionalHolding.qoq_change_shares, Float)),
        ),
        (
            InstitutionalHolding.qoq_change_pct > -100.0,
            cast(InstitutionalHolding.value_usd, Float) * func.abs(InstitutionalHolding.qoq_change_pct)
            / (100.0 + InstitutionalHolding.qoq_change_pct),
        ),
        else_=None,
    )

    filtro = [
        InstitutionalFiling.period_end_date == trimestre,
        InstitutionalHolding.action.in_(azioni),
    ]
    if type_:
        filtro.append(Institutional.type == type_)

    stmt = (
        select(
            InstitutionalHolding.ticker,
            InstitutionalHolding.company_name,
            Institutional.slug,
            Institutional.name,
            InstitutionalHolding.action,
            prima.label("prima"),
            dopo.label("dopo"),
            delta,
            valore.label("valore_op"),
            InstitutionalHolding.qoq_change_pct,
            InstitutionalHolding.value_usd,
            select(func.min(Stock.id)).where(Stock.ticker == InstitutionalHolding.ticker)
            .correlate(InstitutionalHolding).scalar_subquery().label("stock_id"),
        )
        .join(InstitutionalFiling, InstitutionalFiling.id == InstitutionalHolding.filing_id)
        .join(Institutional, Institutional.id == InstitutionalFiling.institutional_id)
        .join(prec, prec.c.iid == InstitutionalFiling.institutional_id)
        .outerjoin(
            pesi_prec,
            and_(
                pesi_prec.c.iid == InstitutionalFiling.institutional_id,
                pesi_prec.c.ticker == InstitutionalHolding.ticker,
            ),
        )
        .where(*filtro)
        .order_by(func.coalesce(valore, 0).desc(), func.abs(dopo - prima).desc())
        .limit(limit)
    )
    righe = db.execute(stmt).all()

    fondi = db.execute(
        select(func.count(func.distinct(InstitutionalFiling.institutional_id)))
        .join(Institutional, Institutional.id == InstitutionalFiling.institutional_id)
        .where(InstitutionalFiling.period_end_date == trimestre, *([Institutional.type == type_] if type_ else []))
    ).scalar() or 0

    return OperazioniTrimestre(
        trimestre=trimestre,
        fondi=int(fondi),
        operazioni=[
            Operazione(
                ticker=r.ticker, company_name=r.company_name, stock_id=r.stock_id,
                institutional_slug=r.slug, institutional_name=r.name, action=r.action,
                peso_prima=round(float(r.prima or 0.0), 2), peso_dopo=round(float(r.dopo or 0.0), 2),
                delta_pp=round(float(r.delta or 0.0), 2),
                valore_operazione=None if r.valore_op is None else int(round(float(r.valore_op))),
                qoq_change_pct=r.qoq_change_pct,
                value_usd=r.value_usd,
            )
            for r in righe
        ],
    )
