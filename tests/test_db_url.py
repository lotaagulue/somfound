from somfound.db import normalize_database_url


def test_bare_postgres_scheme_is_normalized():
    url = "postgres://user:pw@example.supabase.com:6543/postgres"
    assert normalize_database_url(url) == "postgresql://user:pw@example.supabase.com:6543/postgres"


def test_postgresql_scheme_is_left_alone():
    url = "postgresql://user:pw@example.supabase.com:6543/postgres"
    assert normalize_database_url(url) == url


def test_sqlite_url_is_left_alone():
    url = "sqlite:///./somfound.db"
    assert normalize_database_url(url) == url
