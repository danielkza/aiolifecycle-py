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


@init(order=20)
@asynccontextmanager
async def init10() -> AsyncIterator[None]:
    write_json({"init": 20})
    yield
    write_json({"close": 20})


@init(order=10)
@asynccontextmanager
async def init20() -> AsyncIterator[None]:
    write_json({"init": 10})
    yield
    write_json({"close": 10})


@sync()
async def handler(event, context) -> None:
    write_json({"call": {"event": event, "context": context}})


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    for line in sys.stdin:
        call = json.loads(line)
        event = call["event"]
        context = call["context"]

        handler(event, context)
