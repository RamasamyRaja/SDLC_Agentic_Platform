"""Authentication dependencies and request-scoped current-user resolution."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

security = HTTPBearer(auto_error=False)


def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    settings = get_settings()
    if credentials is None:
        if not settings.AUTH_ALLOW_DEV_USER_FALLBACK:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        user = db.query(User).filter(User.email == settings.AUTH_DEV_USER_EMAIL).one_or_none()
        if user is None:
            from app.models.user import UserRole
            user = User(email=settings.AUTH_DEV_USER_EMAIL, full_name="Development User", role=UserRole.ADMIN)
            db.add(user); db.commit(); db.refresh(user)
        if not user.is_active:
            raise HTTPException(status_code=401, detail="User account is inactive")
        return user

    try:
        payload = decode_access_token(credentials.credentials, secret=settings.AUTH_JWT_SECRET)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token") from exc

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive or does not exist")
    return user
