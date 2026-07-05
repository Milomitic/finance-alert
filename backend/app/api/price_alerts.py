"""Price-target alerts CRUD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import PriceAlert, Stock, User
from app.schemas.price_alert import PriceAlertCreate, PriceAlertOut, PriceAlertUpdate
from app.services import price_alert_service

router = APIRouter(tags=["price-alerts"])


def _stock_id_or_404(db: Session, ticker: str) -> int:
    # `ticker` è univoco a livello di catalogo (vedi
    # `services.exchange_codes` + `scripts/dedupe_stocks`):
    # `scalar_one_or_none()` failuoresce se vengono reintrodotti duplicati.
    s = db.execute(
        select(Stock).where(Stock.ticker == ticker)
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
    return s.id


@router.get("/api/stocks/{ticker}/price-alerts", response_model=list[PriceAlertOut])
def list_price_alerts(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PriceAlertOut]:
    stock_id = _stock_id_or_404(db, ticker)
    rows = price_alert_service.list_for_stock(db, stock_id)
    return [PriceAlertOut.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/api/stocks/{ticker}/price-alerts",
    response_model=PriceAlertOut,
    status_code=201,
    dependencies=[Depends(require_json)],
)
def create_price_alert(
    ticker: str,
    body: PriceAlertCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PriceAlertOut:
    stock_id = _stock_id_or_404(db, ticker)
    try:
        pa = price_alert_service.create(
            db, stock_id, target_price=body.target_price,
            direction=body.direction, note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PriceAlertOut.model_validate(pa, from_attributes=True)


@router.patch(
    "/api/price-alerts/{alert_id}",
    response_model=PriceAlertOut,
    dependencies=[Depends(require_json)],
)
def update_price_alert(
    alert_id: int,
    body: PriceAlertUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PriceAlertOut:
    try:
        pa = price_alert_service.update(
            db, alert_id,
            enabled=body.enabled, target_price=body.target_price,
            direction=body.direction, note=body.note,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Price alert not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PriceAlertOut.model_validate(pa, from_attributes=True)


@router.delete(
    "/api/price-alerts/{alert_id}",
    status_code=204,
    dependencies=[Depends(require_json)],
)
def delete_price_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    try:
        price_alert_service.delete(db, alert_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Price alert not found")
