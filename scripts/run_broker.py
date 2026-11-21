"""Dev broker: amqtt on 127.0.0.1:1883 - same engine smoke_test.py uses."""
import asyncio
from amqtt.broker import Broker

config = {
    "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:1883"}},
    "sys_interval": 10,
}

async def main() -> None:
    broker = Broker(config)
    await broker.start()
    print("broker up: 127.0.0.1:1883  (Ctrl+C to stop)")
    await asyncio.Event().wait()

asyncio.run(main())
