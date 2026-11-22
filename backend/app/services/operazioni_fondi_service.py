"""Le operazioni dei fondi nell'ultimo trimestre, dalla piu' rilevante.

La RILEVANZA e' lo spostamento del peso nel portafoglio del fondo, in punti:
peso dopo meno peso prima. Non il valore in dollari, che metterebbe in cima
ogni ritocco dei fondi indice da migliaia di miliardi (un +0,02% di Vanguard
vale piu' dollari di un 10% di un investitore concentrato) e direbbe quanto e'
grande il fondo, non quanto conta la mossa per chi l'ha fatta.

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

from sqlalchemy import and_, case, func, select
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
    qoq_change_pct: float | None
    value_usd: int | None


@dataclass
class OperazioniTrimestre:
    trimestre: date | None
    fondi: int
    operazioni: list[Operazione]


def operazioni_ultimo_trimestre(
    db: Session, *, type_: str | None = None, limit: int = 30,
) -> OperazioniTrimestre:
    """Le operazioni del trimestre piu' recente, per spostamento di peso."""
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

    filtro = [
        InstitutionalFiling.period_end_date == trimestre,
        InstitutionalHolding.action.in_(AZIONI),
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
        .order_by(func.abs(dopo - prima).desc(), func.coalesce(InstitutionalHolding.value_usd, 0).desc())
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
                delta_pp=round(float(r.delta or 0.0), 2), qoq_change_pct=r.qoq_change_pct,
                value_usd=r.value_usd,
            )
            for r in righe
        ],
    )
