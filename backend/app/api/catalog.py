"""Catalog refresh endpoints."""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.db import SessionLocal
from app.models import CatalogRefreshLog, User
from app.schemas.catalog import CatalogStatusOut, IndexStatusOut, RefreshAccepted, RefreshRequest
from app.services.catalog_refresh_service import INDEX_SOURCES, refresh_all, refresh_index

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _run_refresh(index_code: str | None) -> None:
    db = SessionLocal()
    try:
        if index_code is None:
            refresh_all(db)
        else:
            refresh_index(db, index_code)
        db.commit()
    finally:
        db.close()


@router.post("/refresh", status_code=202, response_model=RefreshAccepted, dependencies=[Depends(require_json)])
def trigger(
    payload: RefreshRequest,
    background: BackgroundTasks,
    _user: User = Depends(get_current_user),
) -> RefreshAccepted:
    background.add_task(_run_refresh, payload.index_code)
    return RefreshAccepted(accepted=True)


@router.get("/status", response_model=CatalogStatusOut)
def status(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> CatalogStatusOut:
    items: list[IndexStatusOut] = []
    for code in INDEX_SOURCES:
        last = db.execute(
            select(CatalogRefreshLog)
            .where(CatalogRefreshLog.index_code == code)
            .order_by(CatalogRefreshLog.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        items.append(
            IndexStatusOut(
                index_code=code,
                last_started_at=last.started_at if last else None,
                last_completed_at=last.completed_at if last else None,
                last_status=last.status if last else None,
                stocks_added=last.stocks_added if last else None,
                stocks_updated=last.stocks_updated if last else None,
                stocks_removed=last.stocks_removed if last else None,
                error_message=last.error_message if last else None,
            )
        )
    return CatalogStatusOut(indices=items)
