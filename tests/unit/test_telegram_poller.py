import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from telegram import Chat, Message
from telegram.constants import ChatType

from app.core.config import settings
from app.services.decisions import decision_key
from app.services.channels.telegram_channel import encode_callback
from app.utils.flags import Severity
from app.workers.telegram_poller import telegram_polling_loop


async def test_empty_token_returns_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    res = await telegram_polling_loop()

    assert res.source == "telegram"
    assert res.severity == Severity.INFO


class FakeRedis:
    def __init__(self):
        self.deleted_keys = []

    async def sismember(self, key, member):
        return False

    async def sadd(self, key, member):
        pass

    async def expire(self, key, ttl):
        pass

    async def delete(self, key):
        self.deleted_keys.append(key)

    async def aclose(self):
        pass


class FakeBot:
    def __init__(self, updates):
        self._updates = list(updates)
        self.answered = []
        self.edited = []

    async def get_updates(self, timeout, allowed_updates):
        if self._updates:
            return [self._updates.pop(0)]
        raise asyncio.CancelledError

    async def answer_callback_query(self, cq_id, text):
        self.answered.append((cq_id, text))

    async def edit_message_text(self, chat_id, message_id, text):
        pass
        self.edited.append((chat_id, message_id, text))


class FakeSaver:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass


class FakeGraph:
    def __init__(self):
        self.invocations = []

    async def aget_state(self, config):
        return SimpleNamespace(next=("gate",))

    async def ainvoke(self, command, config):
        self.invocations.append((command, config))


async def test_resume_happy_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "x")

    fake_update = SimpleNamespace(
        update_id=1,
        callback_query=SimpleNamespace(
            id="cq-1",
            data=encode_callback("approve", "run-42", 7),
            message=Message(
                message_id=11,
                date=datetime.now(timezone.utc),
                chat=Chat(id=555, type=ChatType.PRIVATE),
                text="nota",
            ),
        ),
    )
    fake_bot = FakeBot(updates=[fake_update])
    fake_redis = FakeRedis()
    fake_graph = FakeGraph()

    monkeypatch.setattr("app.workers.telegram_poller.Bot", lambda token: fake_bot)
    monkeypatch.setattr("redis.asyncio.Redis", SimpleNamespace(from_url=lambda *a, **k: fake_redis))
    monkeypatch.setattr(
        "app.workers.telegram_poller.AsyncPostgresSaver",
        SimpleNamespace(from_conn_string=lambda dsn: FakeSaver()),
    )
    fake_decision = {"value": True}
    monkeypatch.setattr(
        "app.workers.telegram_poller.handle_decision",
        lambda redis, run_id, rec_id, approved: _fake_handle_decision(fake_decision),
    )
    monkeypatch.setattr("app.workers.telegram_poller.compile_graph", lambda saver: fake_graph)

    flag = await telegram_polling_loop()

    assert flag.message == "telegram poller stopped"
    assert len(fake_graph.invocations) == 1
    command, config = fake_graph.invocations[0]
    assert command.resume == "approved"
    assert config["configurable"]["thread_id"] == "run-42"
    assert ("cq-1", "registrado") in fake_bot.answered
    assert any("aprovado" in text for _, _, text in fake_bot.edited)


async def _fake_handle_decision(decision):
    return decision["value"]


async def test_duplicate_decision_does_not_resume_graph(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "x")

    fake_update = SimpleNamespace(
        update_id=1,
        callback_query=SimpleNamespace(
            id="cq-1",
            data=encode_callback("approve", "run-42", 7)
        )
    )

    fake_bot = FakeBot(updates=[fake_update])
    fake_redis = FakeRedis()
    fake_graph = FakeGraph()

    monkeypatch.setattr("app.workers.telegram_poller.Bot", lambda token: fake_bot)
    monkeypatch.setattr("redis.asyncio.Redis", SimpleNamespace(from_url=lambda *a, **k: fake_redis))
    monkeypatch.setattr(
        "app.workers.telegram_poller.AsyncPostgresSaver",
        SimpleNamespace(from_conn_string=lambda dsn: FakeSaver()),
    )

    fake_decision = {"value": None}
    monkeypatch.setattr(
        "app.workers.telegram_poller.handle_decision",
        lambda redis, run_id, rec_id, approved: _fake_handle_decision(fake_decision),
    )
    monkeypatch.setattr("app.workers.telegram_poller.compile_graph", lambda saver: fake_graph)

    flag = await telegram_polling_loop()

    assert flag.message == "telegram poller stopped"
    assert fake_graph.invocations == []
    assert ("cq-1", "já registrado") in fake_bot.answered


async def test_resume_failure_rollback_survives(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "x")

    fake_update = SimpleNamespace(
        update_id=1,
        callback_query=SimpleNamespace(
            id="cq-1",
            data=encode_callback("approve", "run-42", 7)
        )
    )

    fake_bot = FakeBot(updates=[fake_update])
    fake_redis = FakeRedis()
    fake_graph = FakeGraph()

    monkeypatch.setattr("app.workers.telegram_poller.Bot", lambda token: fake_bot)
    monkeypatch.setattr("redis.asyncio.Redis", SimpleNamespace(from_url=lambda *a, **k: fake_redis))
    monkeypatch.setattr(
        "app.workers.telegram_poller.AsyncPostgresSaver",
        SimpleNamespace(from_conn_string=lambda dsn: FakeSaver()),
    )

    fake_decision = {"value": True}
    monkeypatch.setattr(
        "app.workers.telegram_poller.handle_decision",
        lambda redis, run_id, rec_id, approved: _fake_handle_decision(fake_decision),
    )
    monkeypatch.setattr("app.workers.telegram_poller.compile_graph", lambda saver: fake_graph)

    async def failing_ainvoke(command, config):
        raise RuntimeError("resume blew up")

    fake_graph.ainvoke = failing_ainvoke

    flag = await telegram_polling_loop()

    assert flag.message == "telegram poller stopped"
    assert decision_key(run_id="run-42", rec_id=7) in fake_redis.deleted_keys
    assert ("cq-1", "erro ao processar — tente novamente") in fake_bot.answered
