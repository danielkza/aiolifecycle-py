import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiofiles
from aiofiles.threadpool.text import AsyncTextIOWrapper

from aiolifecycle import init
from aiolifecycle import sync


# Make this lazy as it is only used by json_log_file.
@init(lazy=True)
async def json_log_path() -> str:
    # Run complicated logic to determine path, only once!
    # ....
    return '/tmp/my-file.json'


# Not lazy, will be initialised eagerly at startup
@init()
@asynccontextmanager
async def json_log_file() -> AsyncIterator[AsyncTextIOWrapper]:
    log_path = await json_log_path()
    # File will be open at initialisation, and cleaned up on shutdown
    async with aiofiles.open(log_path, mode='a') as f:
        yield f


@sync()
async def handler():
    log_file = await json_log_file()
    await log_file.write(json.dumps({"message": "hello, world!"}) + "\n")
    await log_file.flush()
