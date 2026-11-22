"""M18: only an explicit testing flag can enable the isolated A01 service."""
from __future__ import annotations

import pytest

from radich.agents import testing_deployment


@pytest.mark.parametrize("flag", [None, "", "no", "true", "YES", "1"])
def test_a01_factory_fails_closed_without_exact_testing_flag(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("RADICH_A01_TESTING_ENABLED", raising=False)
    else:
        monkeypatch.setenv("RADICH_A01_TESTING_ENABLED", flag)
    monkeypatch.setenv("RADICH_API_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/unused")
    with pytest.raises(RuntimeError, match="disabled by default"):
        testing_deployment.build_app()


@pytest.mark.parametrize("missing", ["DATABASE_URL", "RADICH_API_KEY"])
def test_a01_factory_requires_database_and_api_key(monkeypatch, missing):
    monkeypatch.setenv("RADICH_A01_TESTING_ENABLED", "yes")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/unused")
    monkeypatch.setenv("RADICH_API_KEY", "test-secret")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match="are required"):
        testing_deployment.build_app()


def test_explicit_testing_flag_grants_only_existing_server_side_skill(monkeypatch):
    monkeypatch.setenv("RADICH_A01_TESTING_ENABLED", "yes")
    monkeypatch.setenv("DATABASE_URL", "postgresql://host:5432/radich_a01")
    monkeypatch.setenv("RADICH_API_KEY", "test-secret")

    received = {}
    sentinel = object()

    def fake_m17_factory(**kwargs):
        received.update(kwargs)
        return sentinel

    monkeypatch.setattr(testing_deployment, "_build_m17_app", fake_m17_factory)
    assert testing_deployment.build_app() is sentinel
    assert received == {
        "dsn": "postgresql://host:5432/radich_a01",
        "api_key": "test-secret",
        "grant_skill": True,
    }
