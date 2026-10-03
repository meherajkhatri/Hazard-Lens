"""Preflight against Dev 2's real backend: down, wrong key, and ready."""

import socket

import pytest

from cv_engine.config import EngineConfig
from cv_engine.preflight import check
from cv_engine.tests.test_emitter import _start_backend


@pytest.fixture
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable_backend_explains_host_and_network(free_port):
    problems = "\n".join(check(EngineConfig(BACKEND_URL=f"http://localhost:{free_port}")))
    assert "Cannot reach the backend" in problems
    assert "--host 0.0.0.0" in problems
    assert "BACKEND_URL points at this laptop" in problems


def test_wrong_api_key_is_reported(free_port, tmp_path):
    server, thread = _start_backend(free_port, tmp_path, api_key="right")
    try:
        problems = check(EngineConfig(BACKEND_URL=f"http://127.0.0.1:{free_port}", API_KEY="wrong"))
        assert problems and "API key" in problems[0]
    finally:
        server.should_exit = True
        thread.join(5)


def test_ready_when_reachable_and_key_matches(free_port, tmp_path):
    server, thread = _start_backend(free_port, tmp_path, api_key="right")
    try:
        assert check(EngineConfig(BACKEND_URL=f"http://127.0.0.1:{free_port}", API_KEY="right")) == []
    finally:
        server.should_exit = True
        thread.join(5)
