"""docker-compose.yml checks, read as text because no YAML parser is a dependency (AC1).

`docker compose config` with and without the password is run as a command in
/ship-feature, /test-feature and CI.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (REPO_ROOT / "docker-compose.yml").read_text()


def service_block(name: str) -> str:
    """The text of one service, from its header to the next top-level or service key."""
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \S|^\S)", COMPOSE, re.MULTILINE | re.DOTALL)
    assert match, f"service {name} not found"
    return match.group(1)


@pytest.mark.parametrize(
    ("service", "image"),
    [
        ("postgres", "pgvector/pgvector:0.8.7-pg18-trixie"),
        ("redis", "redis:8.8.4-alpine"),
    ],
)
def test_image_is_pinned_to_a_full_tag(service: str, image: str) -> None:
    assert f"image: {image}\n" in service_block(service)


@pytest.mark.parametrize("service", ["postgres", "redis"])
def test_every_published_port_binds_to_localhost(service: str) -> None:
    ports = re.findall(r'^\s+- "([^"]+)"$', service_block(service).split("ports:")[1], re.M)
    assert ports
    assert all(port.startswith("127.0.0.1:") for port in ports)


def test_no_port_is_published_on_all_interfaces() -> None:
    port_lines = re.findall(r'^\s+- "(.*:\d+)"$', COMPOSE, re.MULTILINE)
    assert port_lines
    assert all(line.startswith("127.0.0.1:") for line in port_lines)


@pytest.mark.parametrize("service", ["postgres", "redis"])
def test_service_has_healthcheck_volume_and_memory_limit(service: str) -> None:
    block = service_block(service)
    assert "healthcheck:" in block
    assert re.search(r"volumes:\n\s+(#.*\n\s+)*- \w+_data:/", block)
    assert re.search(r"memory: \d+M", block)


def test_postgres_volume_uses_the_postgres_18_path() -> None:
    assert "- postgres_data:/var/lib/postgresql\n" in service_block("postgres")


@pytest.mark.parametrize("variable", ["POSTGRES_PASSWORD", "REDIS_PASSWORD"])
def test_passwords_are_required(variable: str) -> None:
    assert f"${{{variable}:?Set {variable} in .env}}" in COMPOSE


def test_no_literal_password_in_the_file() -> None:
    for match in re.finditer(r"(?:PASSWORD|REDISCLI_AUTH): (.+)", COMPOSE):
        assert match.group(1).startswith("${")
