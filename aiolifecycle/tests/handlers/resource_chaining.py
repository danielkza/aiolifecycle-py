import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any
from typing import AsyncIterator

from aiolifecycle.handlers import init
from aiolifecycle.handlers import sync


def write_json(data: Any) -> None:
    json.dump(data, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


@init(lazy=True)
@asynccontextmanager
async def init10() -> AsyncIterator[int]:
    write_json({"init": 10})
    yield 10
    write_json({"close": 10})


@init(lazy=True)
async def init20() -> int:
    write_json({"init": 20})
    return 20


@init()
async def init30() -> int:
    value = (await init10()) + (await init20())
    write_json({"init": value})
    return value


@sync()
async def handler(event, context) -> None:
    value = await init30()
    write_json({"value": value})
    write_json({"call": {"event": event, "context": context}})


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    for line in sys.stdin:
        call = json.loads(line)
        event = call["event"]
        context = call["context"]

        handler(event, context)
