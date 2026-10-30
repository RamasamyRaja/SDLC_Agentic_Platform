import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.rbac import Permission, require_permission
from app.schemas.auth import LoginRequest, RegisterRequest, RoleUpdateRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])


def _validate_email(email: str) -> str:
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Invalid email address")
    return email


def _issue_token(user: User) -> TokenResponse:
    settings = get_settings()
    token = create_access_token(
        subject=str(user.id), role=user.role.value,
        secret=settings.AUTH_JWT_SECRET,
        expires_seconds=settings.AUTH_ACCESS_TOKEN_EXPIRE_SECONDS,
    )
    return TokenResponse(access_token=token, expires_in=settings.AUTH_ACCESS_TOKEN_EXPIRE_SECONDS, user=user)


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = _validate_email(payload.email)
    if db.query(User).filter(User.email == email).one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user_count = db.query(User).count()
    role = UserRole.ADMIN if user_count == 0 else UserRole.DEVELOPER
    user = User(email=email, full_name=payload.full_name, password_hash=hash_password(payload.password), role=role)
    db.add(user); db.commit(); db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = _validate_email(payload.email)
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    return _issue_token(user)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@users_router.get("", response_model=list[UserResponse])
def list_users(current_user: User = Depends(require_permission(Permission.USER_READ)), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at).all()


@users_router.patch("/{user_id}/role", response_model=UserResponse)
def update_role(user_id: str, payload: RoleUpdateRequest, current_user: User = Depends(require_permission(Permission.USER_MANAGE)), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and payload.role != UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="An administrator cannot remove their own admin role")
    if user.role == UserRole.ADMIN and payload.role != UserRole.ADMIN:
        active_admins = db.query(User).filter(User.role == UserRole.ADMIN, User.is_active.is_(True)).count()
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last active administrator")
    user.role = payload.role
    db.commit(); db.refresh(user)
    return user


@users_router.patch("/{user_id}/active", response_model=UserResponse)
def set_active(user_id: str, active: bool, current_user: User = Depends(require_permission(Permission.USER_MANAGE)), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and not active:
        raise HTTPException(status_code=400, detail="An administrator cannot deactivate their own account")
    if user.role == UserRole.ADMIN and not active:
        active_admins = db.query(User).filter(User.role == UserRole.ADMIN, User.is_active.is_(True)).count()
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last active administrator")
    user.is_active = active
    db.commit(); db.refresh(user)
    return user
