"""The `llm` marker is skipped by default and runs on request (AC3)."""

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

REPO_ROOT = Path(__file__).resolve().parents[2]

SAMPLE_TESTS = """
import pytest

@pytest.mark.llm
def test_calls_a_real_model():
    raise AssertionError("must not run by default")

def test_plain():
    pass
"""


@pytest.fixture
def sample_project(pytester: pytest.Pytester) -> pytest.Pytester:
    """A throwaway project that uses this repo's real pytest settings."""
    pytester.makepyprojecttoml((REPO_ROOT / "pyproject.toml").read_text())
    pytester.makepyfile(test_sample=SAMPLE_TESTS)
    return pytester


def test_llm_tests_are_deselected_by_default(sample_project: pytest.Pytester) -> None:
    result = sample_project.runpytest()
    result.assert_outcomes(passed=1, deselected=1)


def test_llm_tests_run_when_asked(sample_project: pytest.Pytester) -> None:
    result = sample_project.runpytest("-m", "llm")
    result.assert_outcomes(failed=1, deselected=1)
