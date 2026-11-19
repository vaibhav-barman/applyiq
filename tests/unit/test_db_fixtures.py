"""The database fixtures skip, fail or refuse as designed (AC12, AC13). No Postgres needed."""

from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from tests.db_support import (
    derived_url,
    ensure_database,
    make_test_engine,
    require_test_database,
)

pytest_plugins = ["pytester"]

REPO_ROOT = Path(__file__).resolve().parents[2]
UNREACHABLE_URL = "postgresql+psycopg://applyiq:unused@127.0.0.1:1/applyiq"

SAMPLE_TESTS = """
import pytest

@pytest.mark.db
def test_needs_postgres(db_session):
    raise AssertionError("must not run without Postgres")

def test_plain():
    pass
"""


@pytest.fixture
def sample_project(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A throwaway project with this repo's pytest settings and shared fixtures."""
    pytester.makepyprojecttoml((REPO_ROOT / "pyproject.toml").read_text())
    pytester.makeconftest((REPO_ROOT / "tests" / "conftest.py").read_text())
    pytester.makepyfile(test_sample=SAMPLE_TESTS)
    pytester.syspathinsert(REPO_ROOT)
    for name in ("APP_ENV", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    return pytester


def test_unreachable_postgres_skips_db_tests_with_the_start_hint(
    sample_project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    result = sample_project.runpytest("-rs")
    result.assert_outcomes(passed=1, skipped=1)
    assert result.ret == 0
    result.stdout.fnmatch_lines(["SKIPPED*docker compose up -d postgres*"])
    assert "unused" not in result.stdout.str()


def test_require_services_turns_the_skip_into_a_failure(
    sample_project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    result = sample_project.runpytest("--require-services")
    result.assert_outcomes(passed=1, errors=1)
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*docker compose up -d postgres*"])
    assert "unused" not in result.stdout.str()


def test_without_database_url_other_tests_still_collect_and_pass(
    sample_project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert not (sample_project.path / ".env").exists()
    result = sample_project.runpytest("-rs")
    result.assert_outcomes(passed=1, skipped=1)
    result.stdout.fnmatch_lines(["*DATABASE_URL is missing*"])


def test_derived_url_adds_the_test_suffix() -> None:
    assert derived_url(make_url(UNREACHABLE_URL)).database == "applyiq_test"


@pytest.mark.parametrize(
    "name", ["applyiq", "applyiq_testing", "test_applyiq", "postgres", "applyiq_TEST", "", None]
)
def test_a_database_not_named_test_is_refused(name: str) -> None:
    url = make_url(UNREACHABLE_URL).set(database=name)
    with pytest.raises(RuntimeError, match="not named"):
        require_test_database(url)
    with pytest.raises(RuntimeError, match="not named"):
        make_test_engine(url)


@pytest.mark.parametrize("name", ["applyiq_test", "applyiq_migrations_test"])
def test_a_database_named_test_is_accepted(name: str) -> None:
    url = make_url(UNREACHABLE_URL).set(database=name)
    require_test_database(url)
    assert make_test_engine(url) is not None


def test_the_test_database_never_equals_the_configured_one() -> None:
    base = make_url(UNREACHABLE_URL)
    assert derived_url(base).database != base.database
    assert derived_url(base, "_migrations_test").database == "applyiq_migrations_test"


@pytest.mark.parametrize("name", ["applyiq", "postgres", "template1"])
async def test_ensure_database_refuses_real_database_names_even_when_recreating(
    name: str,
) -> None:
    with pytest.raises(RuntimeError, match="not named"):
        await ensure_database(make_url(UNREACHABLE_URL).set(database=name), recreate=True)


async def test_ensure_database_refuses_before_connecting() -> None:
    with pytest.raises(RuntimeError, match="not named"):
        await ensure_database(make_url(UNREACHABLE_URL), recreate=True)
