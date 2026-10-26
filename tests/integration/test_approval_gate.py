import json
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.graph.pipeline import compile_graph
from app.graph.state import InvalidStateError, create_initial_state

EDITOR_JSON = json.dumps({
    "morning_note": "Morning note candidate text.",
    "recommendation": {
        "action": "buy",
        "justification": "Strong upward signals.",
        "confidence": 0.8
    },
    "confidence_scores": {
        "macro": 0.9,
        "company": 0.85,
        "quant": 0.88,
        "risk": 0.82,
        "overall": 0.86
    }
})


def _tavily_ok():
    from app.services.tavily import TavilyArticle, TavilyResult
    return TavilyResult(
        articles=[TavilyArticle(
            title="Title",
            content="Body text.",
            url="https://example.test",
        )],
        error=None,
    )


def _quant_ok():
    from datetime import UTC, datetime

    from app.services.yfinance import QuoteMetrics, YfinanceResult
    return YfinanceResult(
        metrics=QuoteMetrics(
            pl=8.0, ev_ebitda=6.5, p_vpa=1.2,
            dividend_yield=0.05, dev_ibov=-0.01,
            fetched_at=datetime.now(UTC).isoformat(),
            market_time=datetime.now(UTC),
        ),
        error=None,
    )


@pytest.fixture(scope="function")
async def approval_gate_graph(migrated_db_url):
    dsn = migrated_db_url.replace("postgresql+asyncpg", "postgresql", 1)
    asyncpg_dsn = dsn.replace("postgresql://", "postgresql+asyncpg://")

    test_engine = create_async_engine(asyncpg_dsn, echo=False)
    db_session.engine = test_engine
    db_session.SessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)
    import app.agents.persist as persist_module
    persist_module.SessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)
    import app.agents.approval_gate as approval_gate_module
    approval_gate_module.SessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

    _saver_cm = AsyncPostgresSaver.from_conn_string(dsn)
    _saver = await _saver_cm.__aenter__()
    await _saver.setup()
    _graph = compile_graph(_saver)
    yield _graph
    test_engine.sync_engine.dispose()
    await _saver_cm.__aexit__(None, None, None)


async def test_run_to_interrupt_parks_and_persists(approval_gate_graph, migrated_db_url):
    import uuid

    thread_id = str(uuid.uuid4())
    dsn = migrated_db_url.replace("postgresql+asyncpg", "postgresql", 1)
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=str(uuid.uuid4()),
        morning_note_id=123,
    )
    state["recommendation_id"] = 999999
    state["recommendation"] = {
        "action": "buy",
        "confidence": 0.8,
        "justification": "Strong fundamentals",
    }

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO managers (id, name, email, password_hash) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
            1, "Test Manager", "test@test.com", "hash",
        )
        await conn.execute(
            "INSERT INTO companies (id, ticker, name) "
            "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            10, "TEST", "Test Company",
        )
        await conn.execute(
            "INSERT INTO portfolios (id, manager_id, name) "
            "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            100, 1, "Test Portfolio",
        )
        await conn.execute(
            "INSERT INTO morning_notes (id, portfolio_id, manager_id, company_id, note_text) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
            123, 100, 1, 10, "test note",
        )
        await conn.execute(
            "INSERT INTO recommendations (id, morning_note_id, action, confidence, justification) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
            999999, 123, "buy", 0.8, "Strong fundamentals",
        )
    finally:
        await conn.close()

    with (
        patch("app.agents.macro.TavilyService") as MacroT,
        patch("app.agents.company.TavilyService") as CompT,
        patch("app.agents.quant.YfinanceService") as Yf,
        patch("app.agents.macro.summarize", new=AsyncMock(return_value="mac")),
        patch("app.agents.company.summarize", new=AsyncMock(return_value="comp")),
        patch("app.agents.risk.summarize", new=AsyncMock(return_value="[{}]")),
        patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_JSON)),
        patch("app.agents.send.build_telegram_channel") as fake_channel,
    ):
        MacroT.return_value.search = AsyncMock(return_value=_tavily_ok())
        CompT.return_value.search = AsyncMock(return_value=_tavily_ok())
        Yf.return_value.search = AsyncMock(return_value=_quant_ok())
        fake_channel.return_value = MagicMock()
        fake_channel.return_value.send_note = AsyncMock()

        result = await approval_gate_graph.ainvoke(
            state, config={"configurable": {"thread_id": thread_id}}
        )
        assert "__interrupt__" in result
        snap = await approval_gate_graph.aget_state(
            config={"configurable": {"thread_id": thread_id}}
        )
        assert snap.next == ("approval_gate",)

    conn = await asyncpg.connect(dsn)
    try:
        result2 = await conn.fetch(
            "SELECT * FROM checkpoints WHERE thread_id = $1", thread_id
        )
        assert result2

        result3 = await conn.fetchval(
            "SELECT manager_decision FROM recommendations WHERE id = $1", 999999
        )
        assert result3 == "pending"
    finally:
        await conn.close()


async def test_resume_persists_decision(approval_gate_graph, migrated_db_url):
    import uuid

    thread_id = str(uuid.uuid4())
    dsn = migrated_db_url.replace("postgresql+asyncpg", "postgresql", 1)
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=str(uuid.uuid4()),
        morning_note_id=123,
    )
    state["recommendation_id"] = 999999
    state["recommendation"] = {
        "action": "buy",
        "confidence": 0.8,
        "justification": "Strong fundamentals",
    }

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO managers (id, name, email, password_hash) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
            1, "Test Manager", "test@test.com", "hash",
        )
        await conn.execute(
            "INSERT INTO companies (id, ticker, name) "
            "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            10, "TEST", "Test Company",
        )
        await conn.execute(
            "INSERT INTO portfolios (id, manager_id, name) "
            "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            100, 1, "Test Portfolio",
        )
        await conn.execute(
            "INSERT INTO morning_notes (id, portfolio_id, manager_id, company_id, note_text) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
            123, 100, 1, 10, "test note",
        )
    finally:
        await conn.close()

    with (
        patch("app.agents.macro.TavilyService") as MacroT,
        patch("app.agents.company.TavilyService") as CompT,
        patch("app.agents.quant.YfinanceService") as Yf,
        patch("app.agents.macro.summarize", new=AsyncMock(return_value="mac")),
        patch("app.agents.company.summarize", new=AsyncMock(return_value="comp")),
        patch("app.agents.risk.summarize", new=AsyncMock(return_value="[{}]")),
        patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_JSON)),
        patch("app.agents.send.build_telegram_channel") as fake_channel,
    ):
        MacroT.return_value.search = AsyncMock(return_value=_tavily_ok())
        CompT.return_value.search = AsyncMock(return_value=_tavily_ok())
        Yf.return_value.search = AsyncMock(return_value=_quant_ok())
        fake_channel.return_value = MagicMock()
        fake_channel.return_value.send_note = AsyncMock()

        result = await approval_gate_graph.ainvoke(
            state, config={"configurable": {"thread_id": thread_id}}
        )
        assert "__interrupt__" in result
        rec_id = result["__interrupt__"][0].value["recommendation_id"]

        result2 = await approval_gate_graph.ainvoke(
            Command(resume="approved"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" not in result2
        snap = await approval_gate_graph.aget_state(
            config={"configurable": {"thread_id": thread_id}}
        )
        assert snap.next == ()

    conn = await asyncpg.connect(dsn)
    try:
        decision = await conn.fetchval(
            "SELECT manager_decision FROM recommendations WHERE id = $1", rec_id
        )
        decided_at = await conn.fetchval(
            "SELECT decided_at FROM recommendations WHERE id = $1", rec_id
        )
        channel = await conn.fetchval(
            "SELECT decision_channel FROM recommendations WHERE id = $1", rec_id
        )
        assert decision == "approved"
        assert decided_at is not None
        assert channel == "telegram"
    finally:
        await conn.close()


async def test_replay_is_exactly_once(approval_gate_graph, migrated_db_url):
    import uuid

    from redis.asyncio import Redis

    from app.services.decisions import handle_decision

    thread_id = str(uuid.uuid4())
    dsn = migrated_db_url.replace("postgresql+asyncpg", "postgresql", 1)
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=str(uuid.uuid4()),
        morning_note_id=123,
    )
    state["recommendation_id"] = 999999
    state["recommendation"] = {
        "action": "buy",
        "confidence": 0.8,
        "justification": "Strong fundamentals",
    }

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO managers (id, name, email, password_hash) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
            1, "Test Manager", "test@test.com", "hash",
        )
        await conn.execute(
            "INSERT INTO companies (id, ticker, name) "
            "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            10, "TEST", "Test Company",
        )
        await conn.execute(
            "INSERT INTO portfolios (id, manager_id, name) "
            "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            100, 1, "Test Portfolio",
        )
        await conn.execute(
            "INSERT INTO morning_notes (id, portfolio_id, manager_id, company_id, note_text) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
            123, 100, 1, 10, "test note",
        )
    finally:
        await conn.close()

    with (
        patch("app.agents.macro.TavilyService") as MacroT,
        patch("app.agents.company.TavilyService") as CompT,
        patch("app.agents.quant.YfinanceService") as Yf,
        patch("app.agents.macro.summarize", new=AsyncMock(return_value="mac")),
        patch("app.agents.company.summarize", new=AsyncMock(return_value="comp")),
        patch("app.agents.risk.summarize", new=AsyncMock(return_value="[{}]")),
        patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_JSON)),
        patch("app.agents.send.build_telegram_channel") as fake_channel,
    ):
        MacroT.return_value.search = AsyncMock(return_value=_tavily_ok())
        CompT.return_value.search = AsyncMock(return_value=_tavily_ok())
        Yf.return_value.search = AsyncMock(return_value=_quant_ok())
        fake_channel.return_value = MagicMock()
        fake_channel.return_value.send_note = AsyncMock()

        result = await approval_gate_graph.ainvoke(
            state, config={"configurable": {"thread_id": thread_id}}
        )
        assert "__interrupt__" in result
        rec_id = result["__interrupt__"][0].value["recommendation_id"]

    redis = Redis.from_url("redis://localhost:6379/0", decode_responses=False)
    try:
        first = await handle_decision(redis, thread_id, rec_id, True)
        second = await handle_decision(redis, thread_id, rec_id, True)
        assert first is True
        assert second is None

        snap = await approval_gate_graph.aget_state(
            config={"configurable": {"thread_id": thread_id}}
        )
        assert snap.next == ("approval_gate",)

        conn2 = await asyncpg.connect(dsn)
        try:
            count = await conn2.fetchval(
                "SELECT count(*) FROM recommendations WHERE id = $1", rec_id
            )
            assert count == 1
        finally:
            await conn2.close()
    finally:
        await redis.aclose()


async def test_ghost_resume(approval_gate_graph, migrated_db_url):
    import uuid

    thread_id = str(uuid.uuid4())
    dsn = migrated_db_url.replace("postgresql+asyncpg", "postgresql", 1)
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=str(uuid.uuid4()),
        morning_note_id=123,
    )
    state["recommendation_id"] = 999999
    state["recommendation"] = {
        "action": "buy",
        "confidence": 0.8,
        "justification": "Strong fundamentals",
    }

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO managers (id, name, email, password_hash) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
            1, "Test Manager", "test@test.com", "hash",
        )
        await conn.execute(
            "INSERT INTO companies (id, ticker, name) "
            "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            10, "TEST", "Test Company",
        )
        await conn.execute(
            "INSERT INTO portfolios (id, manager_id, name) "
            "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            100, 1, "Test Portfolio",
        )
        await conn.execute(
            "INSERT INTO morning_notes (id, portfolio_id, manager_id, company_id, note_text) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
            123, 100, 1, 10, "test note",
        )
    finally:
        await conn.close()

    with (
        patch("app.agents.macro.TavilyService") as MacroT,
        patch("app.agents.company.TavilyService") as CompT,
        patch("app.agents.quant.YfinanceService") as Yf,
        patch("app.agents.macro.summarize", new=AsyncMock(return_value="mac")),
        patch("app.agents.company.summarize", new=AsyncMock(return_value="comp")),
        patch("app.agents.risk.summarize", new=AsyncMock(return_value="[{}]")),
        patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_JSON)),
        patch("app.agents.send.build_telegram_channel") as fake_channel,
    ):
        MacroT.return_value.search = AsyncMock(return_value=_tavily_ok())
        CompT.return_value.search = AsyncMock(return_value=_tavily_ok())
        Yf.return_value.search = AsyncMock(return_value=_quant_ok())
        fake_channel.return_value = MagicMock()
        fake_channel.return_value.send_note = AsyncMock()

        result = await approval_gate_graph.ainvoke(
            state, config={"configurable": {"thread_id": thread_id}}
        )
        assert "__interrupt__" in result

        result2 = await approval_gate_graph.ainvoke(
            Command(resume="approved"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" not in result2

        snap = await approval_gate_graph.aget_state(
            config={"configurable": {"thread_id": thread_id}}
        )
        assert snap.next == ()

        ghost_tid = str(uuid.uuid4())
        try:
            await approval_gate_graph.ainvoke(
                Command(resume="approved"),
                config={"configurable": {"thread_id": ghost_tid}},
            )
        except InvalidStateError:
            pass
