import uuid

from app.db.session import SessionLocal
from app.models.user import User


def test_create_and_fetch_user():
    unique_email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    db = SessionLocal()
    try:
        user = User(email=unique_email, full_name="Test User")
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.id is not None
        assert user.is_active is True
        assert user.created_at is not None

        fetched = db.query(User).filter(User.email == unique_email).one()
        assert fetched.id == user.id
    finally:
        db.query(User).filter(User.email == unique_email).delete()
        db.commit()
        db.close()
