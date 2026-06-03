import asyncio
from typing import Dict

# Shared SSE queue registry — maps user_id -> {client_id -> asyncio.Queue}.
# Imported by both main.py (/api/stream endpoint) and routers/internal.py
# (score broadcast) to ensure both operate on the same dict object.
# Story 2.6, FR-MT-11: each user receives only their own scored events.
_sse_queues: Dict[int, Dict[str, asyncio.Queue]] = {}


async def broadcast_new_article(article_data: dict, user_id: int) -> None:
    message = {"type": "new_article", "data": article_data}
    user_queues = _sse_queues.get(user_id)
    if not user_queues:
        return
    dead_clients = []
    for client_id, queue in user_queues.items():
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            dead_clients.append(client_id)
    for client_id in dead_clients:
        user_queues.pop(client_id, None)
