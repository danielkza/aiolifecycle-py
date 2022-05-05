import asyncio

from aiolifecycle import init
from aiolifecycle import sync


@init(order=20)
async def world():
    print('World!')


@init(order=10)
async def hello():
    print('Hello!')


@sync()
async def my_handler() -> None:
    await asyncio.sleep(1)
