"""alembic.ini settings that later migrations rely on."""

import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(REPO_ROOT / "alembic.ini")
    return parser


def test_alembic_ini_holds_no_url_or_logging_sections() -> None:
    ini = load_ini()
    assert "sqlalchemy.url" not in ini["alembic"]
    assert not {"loggers", "handlers", "formatters"} & set(ini.sections())


def test_new_revisions_are_linted_and_formatted_by_ruff() -> None:
    hooks = load_ini()["post_write_hooks"]
    assert [name.strip() for name in hooks["hooks"].split(",")] == ["ruff_fix", "ruff_format"]
    assert hooks["ruff_fix.options"] == "check --fix REVISION_SCRIPT_FILENAME"
    assert hooks["ruff_format.options"] == "format REVISION_SCRIPT_FILENAME"
