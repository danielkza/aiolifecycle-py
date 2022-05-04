import asyncio

from lambda_asyncio import lambda_async_handler


@lambda_async_handler(eager=False)
async def my_handler(event, context) -> None:
    await asyncio.sleep(1)
    return None
