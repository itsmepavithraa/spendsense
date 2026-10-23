"""Settings parsing: cloud database URLs and CORS origins."""
import pytest

from app.config import Settings


def make(**overrides) -> Settings:
    values = {"database_url": "sqlite:///x.db", "secret_key": "s", **overrides}
    return Settings(**values)


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@host:5432/db", "postgresql://u:p@host:5432/db"],
)
def test_cloud_postgres_urls_get_the_driver_added(given):
    assert make(database_url=given).database_url == "postgresql+psycopg2://u:p@host:5432/db"


def test_urls_that_already_name_a_driver_are_left_alone():
    url = "postgresql+psycopg2://u:p@host/db"
    assert make(database_url=url).database_url == url
    assert make(database_url="sqlite:///x.db").database_url == "sqlite:///x.db"


def test_cors_origins_are_split_and_trimmed():
    settings = make(cors_origins="https://a.app , https://b.app,,")
    assert settings.cors_origin_list == ["https://a.app", "https://b.app"]


def test_cors_defaults_to_local_frontend():
    assert make().cors_origin_list == ["http://localhost:3000"]
