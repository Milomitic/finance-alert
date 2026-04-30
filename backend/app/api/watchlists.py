"""Watchlist router."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import User
from app.schemas.stock import StockOut
from app.schemas.watchlist import (
    AddItemsRequest,
    AddItemsResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    WatchlistCreate,
    WatchlistDetailOut,
    WatchlistSummaryOut,
    WatchlistUpdate,
)
from app.services import watchlist_service as ws

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


def _to_detail_out(detail) -> WatchlistDetailOut:
    return WatchlistDetailOut(
        id=detail.id,
        name=detail.name,
        description=detail.description,
        stocks=[StockOut.model_validate(s) for s in detail.stocks],
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )


@router.get("", response_model=list[WatchlistSummaryOut])
def list_all(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[WatchlistSummaryOut]:
    return [
        WatchlistSummaryOut(
            id=s.id,
            name=s.name,
            description=s.description,
            item_count=s.item_count,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in ws.list_watchlists(db, user_id=user.id)
    ]


@router.post(
    "",
    response_model=WatchlistDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_json)],
)
def create(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchlistDetailOut:
    try:
        wl = ws.create_watchlist(
            db, user_id=user.id, name=payload.name, description=payload.description
        )
    except ws.DuplicateName as err:
        raise HTTPException(status_code=409, detail="Watchlist name already exists") from err
    if payload.stock_ids:
        ws.add_items(db, wl.id, payload.stock_ids)
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert detail is not None
    return _to_detail_out(detail)


@router.get("/{wl_id}", response_model=WatchlistDetailOut)
def get_one(
    wl_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> WatchlistDetailOut:
    detail = ws.get_watchlist_detail(db, wl_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return _to_detail_out(detail)


@router.patch(
    "/{wl_id}",
    response_model=WatchlistDetailOut,
    dependencies=[Depends(require_json)],
)
def patch(
    wl_id: int,
    payload: WatchlistUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> WatchlistDetailOut:
    try:
        wl = ws.update_watchlist(db, wl_id, name=payload.name, description=payload.description)
    except ws.DuplicateName as err:
        raise HTTPException(status_code=409, detail="Watchlist name already exists") from err
    if wl is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    db.commit()
    detail = ws.get_watchlist_detail(db, wl_id)
    assert detail is not None
    return _to_detail_out(detail)


@router.delete("/{wl_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    wl_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> Response:
    if not ws.delete_watchlist(db, wl_id):
        raise HTTPException(status_code=404, detail="Watchlist not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{wl_id}/items",
    response_model=AddItemsResponse,
    dependencies=[Depends(require_json)],
)
def add_items(
    wl_id: int,
    payload: AddItemsRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AddItemsResponse:
    if ws.get_watchlist(db, wl_id) is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    added = ws.add_items(db, wl_id, payload.stock_ids)
    db.commit()
    return AddItemsResponse(added=added)


@router.delete("/{wl_id}/items/{stock_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item(
    wl_id: int,
    stock_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    if not ws.remove_item(db, wl_id, stock_id):
        raise HTTPException(status_code=404, detail="Item not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{wl_id}/items/bulk-delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_json)],
)
def bulk_delete(
    wl_id: int,
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BulkDeleteResponse:
    removed = ws.bulk_delete_items(db, wl_id, payload.stock_ids)
    db.commit()
    return BulkDeleteResponse(removed=removed)
