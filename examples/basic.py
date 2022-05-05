import asyncio

from aiolifecycle import sync


@sync()
async def my_handler() -> None:
    await asyncio.sleep(1)
    return None
