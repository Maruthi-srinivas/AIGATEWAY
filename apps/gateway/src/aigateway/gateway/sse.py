from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

HEARTBEAT_SECONDS = 15.0


def sse_event(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


def sse_comment(text: str = "ping") -> str:
    return f": {text}\n\n"


async def with_heartbeat(source: AsyncIterator[str]) -> AsyncIterator[str]:
    iterator = source.__aiter__()
    while True:
        try:
            item = await asyncio.wait_for(iterator.__anext__(), timeout=HEARTBEAT_SECONDS)
        except TimeoutError:
            yield sse_comment()
            continue
        except StopAsyncIteration:
            break
        yield item
