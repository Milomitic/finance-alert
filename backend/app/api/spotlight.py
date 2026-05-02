"""GET /api/dashboard/spotlight — 3 cards for HomePage."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.spotlight import SpotlightCardOut, SpotlightOut
from app.services import spotlight_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/spotlight", response_model=SpotlightOut)
def get_spotlight(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SpotlightOut:
    cards_raw = spotlight_service.build(db)
    cards = [SpotlightCardOut(**c) for c in cards_raw]
    return SpotlightOut(cards=cards)
