from __future__ import annotations
from collections.abc import Generator

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
