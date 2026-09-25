import pytest

import app.workers.pipeline as wp

from unittest.mock import AsyncMock, MagicMock, patch
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class FakeSaverCM:
    def __init__(self, saver):
        self._saver = saver
        self.exited = False

    async def __aenter__(self):
        return self._saver
    
    async def __aexit__(self, *args):
        self.exited = True

@pytest.fixture(autouse=True)
def reset_worker_globals():
    yield
    wp._loop = None
    wp._saver_cm = None
    wp._saver = None
    wp._graph = None


def test_init_wires_globals():
    sentinel_saver = MagicMock(spec=AsyncPostgresSaver, name="fake_saver")
    sentinel_saver.setup = AsyncMock()
    cm = FakeSaverCM(sentinel_saver)

    with patch.object(wp.AsyncPostgresSaver, "from_conn_string", return_value=cm):
        wp.init_pipeline_resources()

    assert wp._loop is not None
    assert wp._saver is sentinel_saver
    assert wp._graph is not None
    sentinel_saver.setup.assert_awaited_once()


def test_init_twice_creates_fresh_resources():
    first_saver = MagicMock(spec=AsyncPostgresSaver)
    second_saver = MagicMock(spec=AsyncPostgresSaver)

    with patch.object(wp.AsyncPostgresSaver, "from_conn_string", return_value=FakeSaverCM(first_saver)):
        wp.init_pipeline_resources()
        wp.shutdown_pipeline_resources()

    with patch.object(wp.AsyncPostgresSaver, "from_conn_string", return_value=FakeSaverCM(second_saver)):
        wp.init_pipeline_resources()
        wp.shutdown_pipeline_resources()

    assert wp._saver is second_saver
    assert wp._saver is not first_saver


def test_shutdown_releases_resources():
    saver = MagicMock(spec=AsyncPostgresSaver)
    cm = FakeSaverCM(saver)

    with patch.object(wp.AsyncPostgresSaver, "from_conn_string", return_value=cm):
        wp.init_pipeline_resources()

    wp.shutdown_pipeline_resources()

    assert cm.exited is True
    assert wp._loop.is_closed()
