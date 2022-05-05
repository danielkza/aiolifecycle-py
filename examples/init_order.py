import asyncio

from aiolifecycle import lambda_async_handler
from aiolifecycle import lambda_async_init


@lambda_async_init(order=20)
async def world():
    print('World!')


@lambda_async_init(order=10)
async def hello():
    print('Hello!')


@lambda_async_handler()
async def my_handler(event, context) -> None:
    await asyncio.sleep(1)
    return None
