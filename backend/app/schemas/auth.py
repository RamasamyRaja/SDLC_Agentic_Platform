import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    # Derived from app.rbac.ROLE_PERMISSIONS — the single source of truth.
    permissions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_permissions(self):
        from app.rbac import permissions_for_role
        self.permissions = permissions_for_role(self.role)
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RoleUpdateRequest(BaseModel):
    role: UserRole
