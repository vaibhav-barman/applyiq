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


@pytest.mark.parametrize("variable", ["POSTGRES_PASSWORD", "APP_DB_PASSWORD", "REDIS_PASSWORD"])
def test_passwords_are_required(variable: str) -> None:
    assert f"${{{variable}:?Set {variable} in .env}}" in COMPOSE


def test_no_literal_password_in_the_file() -> None:
    for match in re.finditer(r"(?:PASSWORD|REDISCLI_AUTH): (.+)", COMPOSE):
        assert match.group(1).startswith("${")


@pytest.mark.parametrize("volume", ["postgres_data", "redis_data"])
def test_named_volumes_are_declared_at_the_top_level(volume: str) -> None:
    top_level = COMPOSE.split("\nvolumes:\n")[-1]
    assert re.search(rf"^  {volume}:", top_level, re.MULTILINE)


@pytest.mark.parametrize("service", ["postgres", "redis"])
def test_healthcheck_has_a_test_command_and_retries(service: str) -> None:
    block = service_block(service).split("healthcheck:")[1]
    assert "test:" in block
    assert "retries:" in block


@pytest.mark.parametrize("service", ["postgres", "redis"])
def test_service_restarts_unless_stopped(service: str) -> None:
    assert "restart: unless-stopped" in service_block(service)


def test_redis_refuses_to_evict_keys() -> None:
    assert "noeviction" in service_block("redis")


def test_postgres_does_not_use_the_old_data_path() -> None:
    assert "/var/lib/postgresql/data" not in COMPOSE


def test_redis_password_is_not_a_process_argument() -> None:
    # `--requirepass` on the command line would show the password in `ps` and `docker top`.
    block = service_block("redis")
    assert "--requirepass" not in block
    assert "exec redis-server - " in block
    assert "requirepass $$REDIS_PASSWORD" in block


def test_postgres_runs_the_app_role_init_script() -> None:
    block = service_block("postgres")
    assert "- ./docker/postgres/initdb:/docker-entrypoint-initdb.d:ro\n" in block
    assert "APP_DB_USER: ${APP_DB_USER:-applyiq_app}" in block


def test_app_role_script_creates_a_non_superuser_without_splicing_secrets() -> None:
    script = (REPO_ROOT / "docker/postgres/initdb/01-app-role.sh").read_text()
    assert "NOSUPERUSER" in script
    assert "NOCREATEROLE" in script
    # psql quotes the values itself; the shell never puts them in the SQL text.
    assert "PASSWORD :'app_password'" in script
    assert "<<'SQL'" in script
    assert "$APP_DB_PASSWORD" not in script.split("<<'SQL'")[1]
