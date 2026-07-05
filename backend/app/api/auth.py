"""Auth router."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.config import settings
from app.core.security import create_session_token
from app.models import User
from app.schemas.auth import LoginRequest, MeResponse
from app.services import login_throttle
from app.services.auth_service import authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", dependencies=[Depends(require_json)])
def login(
    payload: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> dict[str, str]:
    # Throttling brute-force lite (B4-11): dopo N fallimenti consecutivi lo
    # username è in lockout — rifiutiamo PRIMA di verificare le credenziali,
    # così un attaccante non può continuare a provare password durante la
    # finestra. Un 429 non estende la finestra (solo un fallimento reale la
    # fa scorrere).
    retry_after = login_throttle.retry_after_seconds(payload.username)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Troppi tentativi di accesso falliti. Riprova più tardi.",
            headers={"Retry-After": str(retry_after)},
        )
    user = authenticate(db, payload.username, payload.password)
    if user is None:
        login_throttle.record_failure(payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    login_throttle.record_success(payload.username)
    token = create_session_token(user.username)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_days * 86400,
        httponly=True,
        samesite="strict",
        secure=not settings.is_dev,
        path="/",
    )
    return {"username": user.username}


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_json)],
)
def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return response


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=user.username)
