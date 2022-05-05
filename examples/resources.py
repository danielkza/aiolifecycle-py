import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiofiles
from aiofiles.threadpool.text import AsyncTextIOWrapper

from aiolifecycle import lambda_async_handler
from aiolifecycle import lambda_async_init


@lambda_async_init()
@asynccontextmanager
async def json_log_file() -> AsyncIterator[AsyncTextIOWrapper]:
    async with aiofiles.open('/tmp/my-file.json', mode='a') as f:
        yield f


@lambda_async_handler()
async def handler(event, context):
    log_file = await json_log_file()
    await log_file.write(json.dumps(event) + "\n")
    await log_file.flush()
