from __future__ import annotations
from collections.abc import Generator
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

import pytest
from docker.errors import DockerException
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_container() -> Generator[PostgresContainer, None, None]:
    try:
        with PostgresContainer("pgvector/pgvector:pg16") as pg:
            yield pg
    except DockerException as e:
        pytest.skip("Docker daemon not reachable. Start Docker Desktop or configure DOCKER_HOST.")


@pytest.fixture(scope="session")
def migrated_db_url(pg_container: PostgresContainer) -> Generator[str, None, None]:
    url = pg_container.get_connection_url(driver="asyncpg")
    cfg = Config(str(Path("alembic.ini").resolve()))
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
        yield url
    finally:
        if original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_db_url
