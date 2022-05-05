import asyncio

from aiolifecycle import init
from aiolifecycle import sync


@init()
async def my_init() -> None:
    print('Hello, world!')


@sync()
async def my_handler(event, context) -> None:
    await asyncio.sleep(1)
    return None
