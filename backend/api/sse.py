import asyncio
from typing import Dict

# Shared SSE queue registry — maps client_id -> asyncio.Queue.
# Imported by both main.py (/api/stream endpoint) and routers/internal.py
# (score broadcast) to ensure both operate on the same dict object.
_sse_queues: Dict[str, asyncio.Queue] = {}


async def broadcast_new_article(article_data: dict) -> None:
    message = {"type": "new_article", "data": article_data}
    dead_clients = []
    for client_id, queue in _sse_queues.items():
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            dead_clients.append(client_id)
    for client_id in dead_clients:
        _sse_queues.pop(client_id, None)
