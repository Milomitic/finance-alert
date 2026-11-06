"""FastAPI dependencies: DB session, current user."""
import hashlib
import hmac
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import presence
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
    db: Session = Depends(get_db, scope="function"),
) -> User:
    # Release the authentication connection before sending an SSE response.
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        utente = _utente_da_token(request, db)
        if utente is not None:
            db.close()
            return utente
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
    # This function-scoped session is distinct from a route's request-scoped
    # get_db dependency. Return the loaded user detached so a subsequent slow
    # provider call does not reserve even the authentication connection.
    db.close()
    presence.segna_attivita()
    return user


#: I soli metodi che il token del server MCP puo' usare: e' di sola lettura per
#: costruzione, non per convenzione di chi lo usa.
_METODI_LETTURA = frozenset({"GET", "HEAD"})


def _utente_da_token(request: Request, db: Session) -> User | None:
    """L'utente amministratore, se la richiesta porta il token di sola lettura
    del server MCP locale (`Authorization: Bearer ...`). None se non lo porta.

    Tre scelte che non sono dettagli:
    - in produzione sta solo l'IMPRONTA (`mcp_token_sha256`): chi legge il
      Secret o la configurazione non ottiene un token usabile;
    - il confronto e' a tempo costante (`hmac.compare_digest`);
    - qualunque metodo diverso da GET/HEAD e' rifiutato con 403 anche col token
      giusto, cosi' una chiamata che scrive non passa nemmeno per sbaglio.
    Non segna la presenza: non e' una persona che usa l'app."""
    intestazione = request.headers.get("authorization", "")
    if not intestazione.lower().startswith("bearer "):
        return None
    atteso = settings.mcp_token_sha256.strip().lower()
    if not atteso:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non abilitato")
    impronta = hashlib.sha256(intestazione[7:].strip().encode("utf-8")).hexdigest()
    if not hmac.compare_digest(impronta, atteso):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if request.method not in _METODI_LETTURA:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token di sola lettura")
    utente = db.execute(select(User).where(User.username == settings.admin_username)).scalar_one_or_none()
    if utente is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return utente


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
        if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-site mutations are not allowed",
            )
        ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if not ctype and not _has_body(request):
            return  # body-less mutation (no header, no payload) is fine
        if ctype != "application/json":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-Type must be application/json",
            )
