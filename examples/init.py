import asyncio

from lambda_asyncio import lambda_async_handler
from lambda_asyncio import lambda_async_init


@lambda_async_init()
async def my_init() -> None:
    print('Hello, world!')


@lambda_async_handler()
async def my_handler(event, context) -> None:
    await asyncio.sleep(1)
    return None
