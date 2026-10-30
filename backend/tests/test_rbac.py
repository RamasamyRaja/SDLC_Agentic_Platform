import uuid

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.user import UserRole
from app.rbac import Permission, ROLE_PERMISSIONS


def test_password_hash_is_not_plaintext_and_verifies():
    password = "correct horse battery staple"
    encoded = hash_password(password)
    assert encoded != password
    assert verify_password(password, encoded)
    assert not verify_password("wrong", encoded)


def test_jwt_round_trip():
    subject = str(uuid.uuid4())
    token = create_access_token(subject=subject, role=UserRole.DEVELOPER.value, secret="test-secret")
    payload = decode_access_token(token, secret="test-secret")
    assert payload["sub"] == subject
    assert payload["role"] == UserRole.DEVELOPER.value


def test_role_permission_matrix():
    assert Permission.USER_MANAGE in ROLE_PERMISSIONS[UserRole.ADMIN]
    assert Permission.AGENT_RUN in ROLE_PERMISSIONS[UserRole.DEVELOPER]
    assert Permission.AGENT_RUN not in ROLE_PERMISSIONS[UserRole.VIEWER]
    assert Permission.REPOSITORY_READ in ROLE_PERMISSIONS[UserRole.VIEWER]
    assert Permission.REPOSITORY_WRITE not in ROLE_PERMISSIONS[UserRole.VIEWER]
