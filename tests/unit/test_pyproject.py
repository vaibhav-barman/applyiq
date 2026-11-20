"""Project layout and dependency pinning (AC1).

`uv lock --check` is a command, not a test: it needs the uv binary and resolves
against the package index. It is run in /test-feature and in CI.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# name, optional extras, then `==` and a concrete version (no wildcard, no range).
_PINNED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?==[0-9][A-Za-z0-9.+!_-]*$")


def is_pinned(requirement: str) -> bool:
    """True for `name==1.2.3`; environment markers after `;` are ignored."""
    return _PINNED.match(requirement.split(";")[0].strip()) is not None


def load_pyproject() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())


def all_requirements(pyproject: dict[str, Any]) -> list[str]:
    """Runtime dependencies, optional extras and every dependency group (including dev)."""
    requirements: list[str] = list(pyproject["project"].get("dependencies", []))
    for extra in pyproject["project"].get("optional-dependencies", {}).values():
        requirements.extend(extra)
    for group in pyproject.get("dependency-groups", {}).values():
        requirements.extend(item for item in group if isinstance(item, str))
    return requirements


@pytest.mark.parametrize(
    "requirement",
    ["fastapi==0.163.1", "pkg[extra]==1.0", "pkg==1.0.0 ; python_version >= '3.14'", "a-b_c.d==2"],
)
def test_pin_checker_accepts_exact_pins(requirement: str) -> None:
    assert is_pinned(requirement)


@pytest.mark.parametrize(
    "requirement",
    [
        "fastapi",
        "fastapi>=0.163",
        "fastapi~=0.163.1",
        "fastapi==0.163.*",
        "fastapi<=1",
        "fastapi!=1",
    ],
)
def test_pin_checker_rejects_loose_requirements(requirement: str) -> None:
    assert not is_pinned(requirement)


def test_src_directory_is_gone() -> None:
    assert not (REPO_ROOT / "src").exists()


def test_pyproject_has_no_build_system_or_scripts() -> None:
    pyproject = load_pyproject()
    assert "build-system" not in pyproject
    assert "scripts" not in pyproject["project"]
    assert "gui-scripts" not in pyproject["project"]


def test_project_is_not_a_package() -> None:
    assert load_pyproject()["tool"]["uv"]["package"] is False


def test_project_declares_python_314() -> None:
    assert load_pyproject()["project"]["requires-python"] == ">=3.14"


def test_every_dependency_is_pinned_with_double_equals() -> None:
    pyproject = load_pyproject()
    requirements = all_requirements(pyproject)
    unpinned = [requirement for requirement in requirements if not is_pinned(requirement)]
    assert unpinned == []


def test_dev_group_exists_and_is_covered_by_the_pin_check() -> None:
    pyproject = load_pyproject()
    dev = pyproject["dependency-groups"]["dev"]
    assert dev, "the dev group must not be empty"
    assert set(dev) <= set(all_requirements(pyproject))


@pytest.mark.parametrize(
    "requirement",
    ["sqlalchemy[asyncio]==2.1.9", "psycopg[binary]==3.3.9", "alembic==1.20.1"],
)
def test_database_dependencies_are_pinned(requirement: str) -> None:
    assert requirement in load_pyproject()["project"]["dependencies"]


def test_lock_file_is_present() -> None:
    assert (REPO_ROOT / "uv.lock").is_file()
