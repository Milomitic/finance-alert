"""FastAPI dependencies: DB session, current user."""
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import read_session_token
from app.models import User


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        username = read_session_token(token)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        ) from err
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _has_body(request: Request) -> bool:
    """True if the request advertises a body. HTTP/1.1 requires either
    Content-Length or Transfer-Encoding for a body to exist; httpx/fetch
    body-less POSTs send `Content-Length: 0` or omit the header entirely."""
    if request.headers.get("transfer-encoding"):
        return True
    length = request.headers.get("content-length", "").strip()
    return bool(length) and length != "0"


def require_json(request: Request) -> None:
    """CSRF lite: enforce Content-Type: application/json on mutating routes.

    Body-less mutations WITHOUT a Content-Type are allowed (POST /scan/stop,
    DELETE, the admin triggers, ...): the FE client (`frontend/src/api/
    client.ts`) only stamps the header when a body exists, and this exemption
    does not reopen the form-CSRF vector — an HTML form submission always
    carries a Content-Type (x-www-form-urlencoded / multipart / text/plain),
    so a forged form POST still lands in the 415 branch below.
    """
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        ctype = request.headers.get("content-type", "").split(";")[0].strip()
        if not ctype and not _has_body(request):
            return  # body-less mutation (no header, no payload) is fine
        if ctype != "application/json":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-Type must be application/json",
            )
