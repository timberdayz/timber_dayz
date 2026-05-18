import socket

from scripts.validate_migrations_fresh_db import (
    DEFAULT_DOCKER_RUN_TIMEOUT_SECONDS,
    build_temp_postgres_run_command,
    choose_temp_postgres_port,
    is_docker_bind_error,
    start_temp_postgres_container,
)


def test_build_temp_postgres_run_command_exposes_requested_port():
    command = build_temp_postgres_run_command(5433)

    assert command[:4] == ["docker", "run", "--rm", "-d"]
    assert "-p" in command
    assert "5433:5432" in command


def test_start_temp_postgres_container_uses_extended_timeout():
    calls = []

    def fake_run(command, cwd=None, env=None, timeout=0):
        calls.append((command, timeout))
        return 0, "container-id\n"

    container_id = start_temp_postgres_container(5433, run_command=fake_run)

    assert container_id == "container-id"
    assert calls == [
        (build_temp_postgres_run_command(5433), DEFAULT_DOCKER_RUN_TIMEOUT_SECONDS)
    ]


def test_choose_temp_postgres_port_falls_back_when_preferred_is_busy():
    busy_socket = socket.socket()
    busy_socket.bind(("0.0.0.0", 0))
    busy_port = busy_socket.getsockname()[1]
    try:
        selected_port = choose_temp_postgres_port(busy_port)
    finally:
        busy_socket.close()

    assert selected_port != busy_port


def test_is_docker_bind_error_detects_port_allocation_failure():
    assert is_docker_bind_error("Bind for 0.0.0.0:5433 failed: port is already allocated") is True
    assert is_docker_bind_error("some other docker error") is False
