"""Tracked-trade positions CRUD (B3-6). Mirrors price_alerts.py for
auth/error-mapping conventions; the P&L enrichment lives in the service."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import Stock, User
from app.schemas.position import PositionCreate, PositionOut, PositionUpdate
from app.services import position_service

router = APIRouter(tags=["positions"])


def _stock_or_404(db: Session, ticker: str) -> Stock:
    # Defensive read path (see CLAUDE.md): .limit(1).first() tolerates a
    # hypothetical future duplicate-ticker regression on a read-only lookup.
    s = db.execute(
        select(Stock).where(Stock.ticker == ticker).limit(1)
    ).scalars().first()
    if s is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
    return s


@router.post(
    "/api/positions",
    response_model=PositionOut,
    status_code=201,
    dependencies=[Depends(require_json)],
)
def open_position(
    body: PositionCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PositionOut:
    stock = _stock_or_404(db, body.ticker)
    entry = body.entry_price
    if entry is None:
        # Default entry = live price, last stored close as fallback.
        entry = position_service.resolve_entry_price(db, stock)
        if entry is None:
            raise HTTPException(
                status_code=422,
                detail="Nessun prezzo disponibile per il ticker: specifica entry_price.",
            )
    try:
        pos = position_service.open_position(
            db,
            stock_id=stock.id,
            side=body.side,
            entry_price=entry,
            stop_price=body.stop_price,
            target_price=body.target_price,
            size=body.size,
            alert_id=body.alert_id,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PositionOut(**position_service.get_position(db, pos.id))


@router.get("/api/positions", response_model=list[PositionOut])
def list_positions(
    status: str = Query(default="all", pattern=r"^(open|closed|all)$"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PositionOut]:
    return [PositionOut(**row) for row in position_service.list_positions(db, status)]


@router.patch(
    "/api/positions/{position_id}",
    response_model=PositionOut,
    dependencies=[Depends(require_json)],
)
def patch_position(
    position_id: int,
    body: PositionUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PositionOut:
    if body.close:
        exit_price = body.exit_price
        try:
            if exit_price is None:
                # Default exit = live price / last close of the position's stock.
                enriched = position_service.get_position(db, position_id)
                stock = _stock_or_404(db, enriched["ticker"])
                exit_price = position_service.resolve_entry_price(db, stock)
                if exit_price is None:
                    raise HTTPException(
                        status_code=422,
                        detail="Nessun prezzo disponibile: specifica exit_price.",
                    )
            pos = position_service.close_position(
                db, position_id, exit_price=exit_price, exit_reason="manual"
            )
        except LookupError:
            raise HTTPException(status_code=404, detail="Position not found") from None
        except ValueError as e:
            # "already closed" is a state conflict, not a validation error.
            detail = str(e)
            status_code = 409 if "already closed" in detail else 422
            raise HTTPException(status_code=status_code, detail=detail) from e
        return PositionOut(**position_service.get_position(db, pos.id))

    try:
        pos = position_service.update_position(
            db, position_id,
            stop_price=body.stop_price,
            target_price=body.target_price,
            notes=body.notes,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Position not found") from None
    except ValueError as e:
        detail = str(e)
        status_code = 409 if "already closed" in detail else 422
        raise HTTPException(status_code=status_code, detail=detail) from e
    return PositionOut(**position_service.get_position(db, pos.id))


@router.delete(
    "/api/positions/{position_id}",
    status_code=204,
    dependencies=[Depends(require_json)],
)
def delete_position(
    position_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    try:
        position_service.delete_position(db, position_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Position not found") from None
