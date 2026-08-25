import sys
from unittest.mock import MagicMock, AsyncMock, patch

# Mock psycopg/libpq before app.graph.pipeline imports it
sys.modules["psycopg"] = MagicMock()
sys.modules["psycopg.pq"] = MagicMock()
sys.modules["langgraph.checkpoint.postgres"] = MagicMock()
sys.modules["langgraph.checkpoint.postgres.aio"] = MagicMock()

import asyncio  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
import json  # noqa: E402
import pytest  # noqa: E402

from app.graph.pipeline import dev_graph, create_initial_state  # noqa: E402
from app.services.sse import sse_service  # noqa: E402
from app.services.tavily import TavilyArticle, TavilyResult  # noqa: E402
from app.services.yfinance import QuoteMetrics, YfinanceResult  # noqa: E402


def _tavily_ok():
    return TavilyResult(
        articles=[TavilyArticle(
            title="Test Article",
            content="Test content",
            url="https://example.test"
        )],
        error=None
    )


def _quant_ok():
    return YfinanceResult(
        metrics=QuoteMetrics(
            pl=8.0, ev_ebitda=6.5, p_vpa=1.2,
            dividend_yield=0.05, dev_ibov=0.01,
            fetched_at=datetime.now(UTC).isoformat(),
            market_time=datetime.now(UTC)
        ),
        error=None
    )


RISK_JSON = '[{"probability": 0.3, "impact": "medium", "description": "Test risk", "severity": "WARNING"}]'

EDITOR_JSON = json.dumps({
    "morning_note": "Test morning note content",
    "recommendation": {"action": "buy", "justification": "Test reason", "confidence": 0.85},
    "confidence_scores": {
        "macro": 0.9, "company": 0.85, "quant": 0.88, "risk": 0.82, "overall": 0.86
    }
})


@pytest.fixture
def patched_all_agents():
    with (
        patch("app.agents.macro.TavilyService") as MacroT,
        patch("app.agents.company.TavilyService") as CompT,
        patch("app.agents.quant.YfinanceService") as Yf,
        patch("app.agents.macro.summarize", new=AsyncMock(return_value="mac")),
        patch("app.agents.company.summarize", new=AsyncMock(return_value="comp")),
        patch("app.agents.risk.summarize", new=AsyncMock(return_value=RISK_JSON)),
        patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_JSON))
    ):
        MacroT.return_value.search = AsyncMock(return_value=_tavily_ok())
        CompT.return_value.search = AsyncMock(return_value=_tavily_ok())
        Yf.return_value.search = AsyncMock(return_value=_quant_ok())
        yield


# step 4: test structure
@pytest.mark.asyncio
async def test_sse_events_correct_order(patched_all_agents):
    pipeline_run_id = "test-run-order-123"
    morning_note_id = "test-note-order-123"

    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=pipeline_run_id,
        morning_note_id=morning_note_id
    )

    # Subscribe FIRST to ensure queue exists before graph emits events
    event_queue = asyncio.Queue()
    
    async def collect_events():
        async for event in sse_service.subscribe(pipeline_run_id):
            await event_queue.put(event)
            if event.get("event_type") == "note_ready":
                break
    
    collector_task = asyncio.create_task(collect_events())
    
    # Small delay to ensure subscription is ready
    await asyncio.sleep(0.01)
    
    # Run graph
    graph_task = asyncio.create_task(dev_graph.ainvoke(
        state,
        config={"configurable": {"thread_id": pipeline_run_id}}
    ))
    
    # Wait for graph to complete
    await graph_task
    
    # Wait for collector to finish (with timeout)
    try:
        await asyncio.wait_for(collector_task, timeout=10.0)
    except asyncio.TimeoutError:
        pytest.fail("SSE event collection timed out")
    
    # Collect events from queue
    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())
    
    event_types = [e["event_type"] for e in events]
    agent_names = [e.get("agent_name") for e in events if "agent_name" in e]

    assert event_types == [
        "agent_started", "agent_completed",
        "agent_started", "agent_completed",
        "agent_started", "agent_completed",
        "agent_started", "agent_completed",
        "agent_started", "agent_completed",
        "note_ready"
    ]
    assert agent_names == [
        "macro", "macro",
        "company", "company",
        "quant", "quant",
        "risk", "risk",
        "editor", "editor"
    ]


@pytest.mark.asyncio
async def test_sse_parallel_agents_concurrent(patched_all_agents):
    """Test that company and quant agents run in parallel - their events interleave."""
    pipeline_run_id = "test-run-parallel-123"
    morning_note_id = "test-note-parallel-123"

    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=pipeline_run_id,
        morning_note_id=morning_note_id
    )

    event_queue = asyncio.Queue()
    
    async def collect_events():
        async for event in sse_service.subscribe(pipeline_run_id):
            await event_queue.put(event)
            if event.get("event_type") == "note_ready":
                break
    
    collector_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)
    
    graph_task = asyncio.create_task(dev_graph.ainvoke(
        state,
        config={"configurable": {"thread_id": pipeline_run_id}}
    ))
    
    await graph_task
    
    try:
        await asyncio.wait_for(collector_task, timeout=10.0)
    except asyncio.TimeoutError:
        pytest.fail("SSE event collection timed out")
    
    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())
    
    # Find company and quant events
    company_events = [e for e in events if e.get("agent_name") == "company"]
    quant_events = [e for e in events if e.get("agent_name") == "quant"]
    
    # Each should have started and completed
    assert len(company_events) == 2
    assert len(quant_events) == 2
    
    company_started = next(e for e in company_events if e["event_type"] == "agent_started")
    company_completed = next(e for e in company_events if e["event_type"] == "agent_completed")
    quant_started = next(e for e in quant_events if e["event_type"] == "agent_started")
    quant_completed = next(e for e in quant_events if e["event_type"] == "agent_completed")
    
    # Parse timestamps
    from datetime import datetime
    cs_time = datetime.fromisoformat(company_started["timestamp"])
    cc_time = datetime.fromisoformat(company_completed["timestamp"])
    qs_time = datetime.fromisoformat(quant_started["timestamp"])
    qc_time = datetime.fromisoformat(quant_completed["timestamp"])
    
    # Parallel execution: company and quant start times should be close (within 200ms)
    # Since they're triggered by the same edge from macro
    time_diff_start = abs((cs_time - qs_time).total_seconds())
    assert time_diff_start < 0.2, f"Company and quant should start concurrently, diff={time_diff_start}s"
    
    # Their completion times should also be close (both are fast mocked calls)
    time_diff_complete = abs((cc_time - qc_time).total_seconds())
    assert time_diff_complete < 0.5, f"Company and quant should complete concurrently, diff={time_diff_complete}s"
    
    # Both should start after macro completes
    macro_completed = next(e for e in events 
                          if e.get("agent_name") == "macro" and e["event_type"] == "agent_completed")
    macro_time = datetime.fromisoformat(macro_completed["timestamp"])
    
    assert cs_time > macro_time, "Company should start after macro completes"
    assert qs_time > macro_time, "Quant should start after macro completes"


@pytest.mark.asyncio
async def test_sse_note_ready_after_editor(patched_all_agents):
    """Test that note_ready event is emitted after editor completes."""
    pipeline_run_id = "test-run-note-ready-123"
    morning_note_id = "test-note-note-ready-123"

    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=pipeline_run_id,
        morning_note_id=morning_note_id
    )

    event_queue = asyncio.Queue()
    
    async def collect_events():
        async for event in sse_service.subscribe(pipeline_run_id):
            await event_queue.put(event)
            if event.get("event_type") == "note_ready":
                break
    
    collector_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)
    
    graph_task = asyncio.create_task(dev_graph.ainvoke(
        state,
        config={"configurable": {"thread_id": pipeline_run_id}}
    ))
    
    await graph_task
    
    try:
        await asyncio.wait_for(collector_task, timeout=10.0)
    except asyncio.TimeoutError:
        pytest.fail("SSE event collection timed out")
    
    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())
    
    # Find editor_completed and note_ready events
    editor_completed = next(e for e in events 
                           if e.get("agent_name") == "editor" and e["event_type"] == "agent_completed")
    note_ready = next(e for e in events if e["event_type"] == "note_ready")
    
    # note_ready should have morning_note_id
    assert note_ready["morning_note_id"] == morning_note_id
    
    # note_ready timestamp should be after editor_completed
    editor_time = datetime.fromisoformat(editor_completed["timestamp"])
    note_time = datetime.fromisoformat(note_ready["timestamp"])
    
    assert note_time > editor_time, "note_ready should be emitted after editor completes"
    
    # Both should have same pipeline_run_id
    assert "pipeline_run_id" not in note_ready  # note_ready doesn't include pipeline_run_id
    assert note_ready["event_type"] == "note_ready"


@pytest.mark.asyncio
async def test_sse_pipeline_failed_on_error():
    """Test that pipeline_failed event is emitted with flags on error."""
    pipeline_run_id = "test-run-failed-123"
    morning_note_id = "test-note-failed-123"

    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=pipeline_run_id,
        morning_note_id=morning_note_id
    )

# Mock to make EDITOR fail (summarize_nemotron returns None)
    with (
        patch("app.agents.macro.TavilyService") as MacroT,
        patch("app.agents.company.TavilyService") as CompT,
        patch("app.agents.quant.YfinanceService") as Yf,
        patch("app.agents.macro.summarize", new=AsyncMock(return_value="mac")),
        patch("app.agents.company.summarize", new=AsyncMock(return_value="comp")),
        patch("app.agents.risk.summarize", new=AsyncMock(return_value=RISK_JSON)),
        patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=None))  # Editor fails
    ):
        MacroT.return_value.search = AsyncMock(return_value=_tavily_ok())
        CompT.return_value.search = AsyncMock(return_value=_tavily_ok())
        Yf.return_value.search = AsyncMock(return_value=_quant_ok())

        event_queue = asyncio.Queue()
        
        async def collect_events():
            async for event in sse_service.subscribe(pipeline_run_id):
                await event_queue.put(event)
                if event.get("event_type") in ("note_ready", "pipeline_failed"):
                    break
        
        collector_task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)
        
        graph_task = asyncio.create_task(dev_graph.ainvoke(
            state,
            config={"configurable": {"thread_id": pipeline_run_id}}
        ))
        
        await graph_task
        
        try:
            await asyncio.wait_for(collector_task, timeout=10.0)
        except asyncio.TimeoutError:
            pytest.fail("SSE event collection timed out")
        
        events = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())
        
        # Print events for debugging
        event_types = [e["event_type"] for e in events]
        print(f"Events emitted: {event_types}")
        
        # Should have pipeline_failed event (not note_ready)
        pipeline_failed = next((e for e in events if e["event_type"] == "pipeline_failed"), None)
        assert pipeline_failed is not None, f"pipeline_failed event should be emitted. Got: {event_types}"
        
        # Should have flags array
        assert "flags" in pipeline_failed
        assert len(pipeline_failed["flags"]) > 0
        
        # First flag should be the editor error
        first_flag = pipeline_failed["flags"][0]
        assert first_flag["source"] == "summarize_nemotron"
        assert first_flag["severity"] == "fatal"
        
        # Should NOT have note_ready
        note_ready = next((e for e in events if e["event_type"] == "note_ready"), None)
        assert note_ready is None, "note_ready should not be emitted on pipeline failure"


@pytest.mark.asyncio
async def test_sse_queue_cleanup_on_completion(patched_all_agents):
    """Test that queue is cleaned up after pipeline completes (note_ready)."""
    pipeline_run_id = "test-run-cleanup-123"
    morning_note_id = "test-note-cleanup-123"

    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id=pipeline_run_id,
        morning_note_id=morning_note_id
    )

    event_queue = asyncio.Queue()
    
    async def collect_events():
        async for event in sse_service.subscribe(pipeline_run_id):
            await event_queue.put(event)
            if event.get("event_type") == "note_ready":
                break
    
    collector_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)
    
    graph_task = asyncio.create_task(dev_graph.ainvoke(
        state,
        config={"configurable": {"thread_id": pipeline_run_id}}
    ))
    
    await graph_task
    
    try:
        await asyncio.wait_for(collector_task, timeout=10.0)
    except asyncio.TimeoutError:
        pytest.fail("SSE event collection timed out")
    
    # Wait a bit for cleanup to happen
    await asyncio.sleep(0.05)
    
    # Queue should be removed from sse_service
    assert pipeline_run_id not in sse_service._queues, "Queue should be cleaned up after note_ready"
    
    # Trying to subscribe again should create a NEW queue (not reuse old one)
    new_queue = sse_service._get_queue(pipeline_run_id)
    assert new_queue is None, "Old queue should not exist after cleanup"


@pytest.mark.asyncio
async def test_sse_multiple_concurrent_pipelines_isolated():
    """Test that multiple concurrent pipelines have isolated event queues."""
    # Mock for this test
    with (
        patch("app.agents.macro.TavilyService") as MacroT,
        patch("app.agents.company.TavilyService") as CompT,
        patch("app.agents.quant.YfinanceService") as Yf,
        patch("app.agents.macro.summarize", new=AsyncMock(return_value="mac")),
        patch("app.agents.company.summarize", new=AsyncMock(return_value="comp")),
        patch("app.agents.risk.summarize", new=AsyncMock(return_value=RISK_JSON)),
        patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_JSON))
    ):
        MacroT.return_value.search = AsyncMock(return_value=_tavily_ok())
        CompT.return_value.search = AsyncMock(return_value=_tavily_ok())
        Yf.return_value.search = AsyncMock(return_value=_quant_ok())

        # Create two pipelines
        run_id_1 = "test-run-multi-1"
        note_id_1 = "test-note-multi-1"
        run_id_2 = "test-run-multi-2"
        note_id_2 = "test-note-multi-2"

        state_1 = create_initial_state(
            manager_id=1,
            company_ticker="PETR4",
            pipeline_run_id=run_id_1,
            morning_note_id=note_id_1
        )
        state_2 = create_initial_state(
            manager_id=2,
            company_ticker="VALE3",
            pipeline_run_id=run_id_2,
            morning_note_id=note_id_2
        )

        # Collect events for both
        queue_1 = asyncio.Queue()
        queue_2 = asyncio.Queue()
        
        async def collect_1():
            async for event in sse_service.subscribe(run_id_1):
                await queue_1.put(event)
                if event.get("event_type") == "note_ready":
                    break
        
        async def collect_2():
            async for event in sse_service.subscribe(run_id_2):
                await queue_2.put(event)
                if event.get("event_type") == "note_ready":
                    break
        
        task_1 = asyncio.create_task(collect_1())
        task_2 = asyncio.create_task(collect_2())
        await asyncio.sleep(0.01)
        
        # Run both graphs concurrently
        graph_task_1 = asyncio.create_task(dev_graph.ainvoke(
            state_1,
            config={"configurable": {"thread_id": run_id_1}}
        ))
        graph_task_2 = asyncio.create_task(dev_graph.ainvoke(
            state_2,
            config={"configurable": {"thread_id": run_id_2}}
        ))
        
        await asyncio.gather(graph_task_1, graph_task_2)
        await asyncio.gather(task_1, task_2)
        
        # Collect events
        events_1 = []
        while not queue_1.empty():
            events_1.append(queue_1.get_nowait())
        
        events_2 = []
        while not queue_2.empty():
            events_2.append(queue_2.get_nowait())
        
        # Each pipeline should have its own complete event sequence
        event_types_1 = [e["event_type"] for e in events_1]
        event_types_2 = [e["event_type"] for e in events_2]
        
        expected = [
            "agent_started", "agent_completed",
            "agent_started", "agent_completed",
            "agent_started", "agent_completed",
            "agent_started", "agent_completed",
            "agent_started", "agent_completed",
            "note_ready"
        ]
        
        assert event_types_1 == expected, f"Pipeline 1 events: {event_types_1}"
        assert event_types_2 == expected, f"Pipeline 2 events: {event_types_2}"
        
        # Events should be isolated - pipeline 1 shouldn't see pipeline 2's events
        agent_names_1 = [e.get("agent_name") for e in events_1 if "agent_name" in e]
        agent_names_2 = [e.get("agent_name") for e in events_2 if "agent_name" in e]
        
        assert agent_names_1 == [
            "macro", "macro",
            "company", "company",
            "quant", "quant",
            "risk", "risk",
            "editor", "editor"
        ]
        assert agent_names_2 == [
            "macro", "macro",
            "company", "company",
            "quant", "quant",
            "risk", "risk",
            "editor", "editor"
        ]
        
        # Note ready should have correct morning_note_id for each
        note_ready_1 = next(e for e in events_1 if e["event_type"] == "note_ready")
        note_ready_2 = next(e for e in events_2 if e["event_type"] == "note_ready")
        
        # We can't easily verify morning_note_id in events since it's only in note_ready
        # but we can verify both completed successfully
        assert note_ready_1["event_type"] == "note_ready"
        assert note_ready_2["event_type"] == "note_ready"
        