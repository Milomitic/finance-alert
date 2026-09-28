"""Il contatore d'uso delle pagine (FA-114): il frontend dice quale pagina si e' aperta.

Il riepilogo NON ha un endpoint suo: viaggia nello snapshot di
`/api/platform/health`, cosi' la scheda della Diagnostica arriva insieme alle
altre e non fa saltare la pagina quando risponde (la lezione di FA-106).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core import rotte
from app.models import User
from app.services import uso_pagine_service

router = APIRouter(prefix="/api/uso", tags=["uso"])


class PaginaIn(BaseModel):
    #: Il pathname del browser. Lungo quanto un ticker o uno slug permettono;
    #: la riduzione a una forma di cardinalita' limitata la fa il server.
    path: str = Field(min_length=1, max_length=200)
    vista: str | None = Field(default=None, max_length=40)


@router.post("/pagina", status_code=202, dependencies=[Depends(require_json)])
def registra_pagina(
    payload: PaginaIn,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, str | None]:
    chiave = rotte.rotta_uso(payload.path, payload.vista)
    if chiave is not None:
        uso_pagine_service.registra(db, chiave)
    return {"rotta": chiave}
