import asyncio
from typing import AsyncGenerator


class SSEService:
    """In-memory SSE event broker for pipeline progress streaming.
    
    Uses asyncio.Queue per pipeline_run_id to buffer events between
    graph nodes (producers) and SSE endpoint (consumer).
    """
    
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
    
    def _get_queue(self, pipeline_run_id: str) -> asyncio.Queue | None:
        """Get existing queue for pipeline_run_id, or None if not exists."""
        return self._queues.get(pipeline_run_id)
    
    def _get_or_create_queue(self, pipeline_run_id: str) -> asyncio.Queue:
        """Get existing queue or create new one for pipeline_run_id."""
        if pipeline_run_id not in self._queues:
            self._queues[pipeline_run_id] = asyncio.Queue()
        return self._queues[pipeline_run_id]
    
    async def emit_event(self, pipeline_run_id: str, event: dict) -> None:
        """Emit an event to the pipeline's queue.
        
        Called by graph nodes. If no queue exists (no subscriber yet),
        event is dropped for MVP simplicity.
        """
        queue = self._get_queue(pipeline_run_id)
        if queue is not None:
            await queue.put(event)
        # else: drop event (no active SSE connection)
    
    async def subscribe(self, pipeline_run_id: str) -> AsyncGenerator[dict, None]:
        """Subscribe to events for a pipeline_run_id.
        
        Yields events as they arrive. Used by SSE endpoint.
        Cleans up queue when generator closes (client disconnects).
        """
        queue = self._get_or_create_queue(pipeline_run_id)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            # Generator closed (client disconnected) - cleanup
            self.cleanup(pipeline_run_id)
    
    def cleanup(self, pipeline_run_id: str) -> None:
        """Remove queue for pipeline_run_id.
        
        Called on pipeline completion (note_ready) or failure (pipeline_failed).
        """
        self._queues.pop(pipeline_run_id, None)


# Module-level singleton instance
sse_service = SSEService()