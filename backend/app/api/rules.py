"""Rules API: CRUD on Tier 1 globals and Tier 2 overrides."""
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import Rule, User
from app.schemas.rule import RuleCreate, RuleOut, RuleUpdate

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _to_out(r: Rule) -> RuleOut:
    return RuleOut(
        id=r.id,
        watchlist_id=r.watchlist_id,
        kind=r.kind,
        params=json.loads(r.params or "{}"),
        enabled=r.enabled,
        expression=json.loads(r.expression) if r.expression else None,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=list[RuleOut])
def list_rules(
    watchlist_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RuleOut]:
    """No query: Tier 1 globals (watchlist_id IS NULL).
    With watchlist_id: Tier 2 overrides for that watchlist."""
    if watchlist_id is None:
        rows = (
            db.execute(select(Rule).where(Rule.watchlist_id.is_(None)).order_by(Rule.kind))
            .scalars()
            .all()
        )
    else:
        rows = (
            db.execute(
                select(Rule).where(Rule.watchlist_id == watchlist_id).order_by(Rule.kind)
            )
            .scalars()
            .all()
        )
    return [_to_out(r) for r in rows]


@router.post(
    "",
    response_model=RuleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_json)],
)
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RuleOut:
    # Uniqueness check is enforced API-side only for atomic kinds: a watchlist
    # can hold at most one rsi_oversold, golden_cross, etc. Composite rules are
    # exempt — multiple composites with different expressions can coexist in the
    # same scope.
    if payload.kind != "composite":
        if payload.watchlist_id is None:
            existing = db.execute(
                select(Rule).where(Rule.watchlist_id.is_(None), Rule.kind == payload.kind)
            ).scalar_one_or_none()
        else:
            existing = db.execute(
                select(Rule).where(
                    Rule.watchlist_id == payload.watchlist_id, Rule.kind == payload.kind
                )
            ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=409, detail="Rule already exists for this (watchlist, kind)"
            )
    r = Rule(
        watchlist_id=payload.watchlist_id,
        kind=payload.kind,
        params=json.dumps(payload.params),
        enabled=payload.enabled,
        expression=json.dumps(payload.expression) if payload.expression else None,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _to_out(r)


@router.patch("/{rule_id}", response_model=RuleOut, dependencies=[Depends(require_json)])
def patch_rule(
    rule_id: int,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RuleOut:
    r = db.execute(select(Rule).where(Rule.id == rule_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if payload.kind is not None:
        r.kind = payload.kind
    if payload.enabled is not None:
        r.enabled = payload.enabled
    if payload.params is not None:
        r.params = json.dumps(payload.params)
    # expression: PATCH supports both setting (dict) and explicit clearing.
    # Pydantic doesn't distinguish "field omitted" from "field set to null", so
    # we use model_fields_set to detect whether the client sent the key at all.
    if "expression" in payload.model_fields_set:
        r.expression = json.dumps(payload.expression) if payload.expression else None
    db.commit()
    db.refresh(r)
    return _to_out(r)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    r = db.execute(select(Rule).where(Rule.id == rule_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(r)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
