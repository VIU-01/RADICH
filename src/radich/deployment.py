"""M15.2: PostgreSQL-backed ASGI application factory for remote Linux deployment.

Connections are short-lived per operation, not shared between FastAPI threads.
"""
from __future__ import annotations

import os

import psycopg

from .api import create_app
from .demo import build_demo_runner
from .persistence.postgres import PostgresRunRepository


class DatabaseRepository:
    def __init__(self, dsn: str):
        if not dsn:
            raise ValueError("DATABASE_URL is required")
        self.dsn = dsn

    def initialize_schema(self):
        with psycopg.connect(self.dsn) as connection:
            PostgresRunRepository(connection).initialize_schema()

    def get_run(self, run_id):
        with psycopg.connect(self.dsn) as connection:
            return PostgresRunRepository(connection).get_run(run_id)

    def save_result(self, result):
        with psycopg.connect(self.dsn) as connection:
            PostgresRunRepository(connection).save_result(result)


class PersistedDemoRunner:
    def __init__(self, repository):
        self.repository = repository

    def run(self, run_id, initial_payloads):
        result = build_demo_runner(run_id).run(run_id, initial_payloads)
        self.repository.save_result(result)
        return result


def build_app():
    api_key = os.environ.get("RADICH_API_KEY", "")
    dsn = os.environ.get("DATABASE_URL", "")
    if not api_key or not dsn:
        raise RuntimeError("RADICH_API_KEY and DATABASE_URL are required")
    repository = DatabaseRepository(dsn)
    repository.initialize_schema()
    return create_app(
        runner=PersistedDemoRunner(repository),
        repository=repository,
        api_key=api_key,
    )
