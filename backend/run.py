"""Windows-safe entrypoint for the backend. Use this instead of bare `uvicorn`.

Why this file exists: uvicorn 0.54 hardcodes `asyncio.ProactorEventLoop` on
Windows (see `uvicorn/loops/asyncio.py`) and ignores the event-loop policy
entirely. ProactorEventLoop has no `add_reader`/`add_writer`, which is exactly
how aiomqtt drives its socket -- so with a bare `uvicorn` command MQTT ingest
dies with NotImplementedError and every connection attempt silently times out.
Setting a policy does not help; you have to hand uvicorn a different loop.

`detection/main.py` needs the opposite treatment (it calls asyncio.run() itself,
which does respect the policy) -- keep the two fixes separate.

    python run.py            # local dev
    python run.py --reload   # local dev with reload
"""

import asyncio
import os
import sys

import uvicorn


def selector_or_default() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        loop="run:selector_or_default",
        reload="--reload" in sys.argv,
    )