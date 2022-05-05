import asyncio

from aiolifecycle import lambda_async_handler


@lambda_async_handler()
async def my_handler(event, context) -> None:
    await asyncio.sleep(1)
    return None
