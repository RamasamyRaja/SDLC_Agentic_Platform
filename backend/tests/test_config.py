from app.core.config import get_settings


def test_settings_load_and_cache():
    settings_a = get_settings()
    settings_b = get_settings()
    assert settings_a is settings_b  # lru_cache should return the same instance


def test_database_uri_built_from_parts():
    settings = get_settings()
    if settings.DATABASE_URL:
        assert settings.sqlalchemy_database_uri == settings.DATABASE_URL
    else:
        uri = settings.sqlalchemy_database_uri
        assert uri.startswith("postgresql+psycopg2://")
        assert settings.POSTGRES_DB in uri
