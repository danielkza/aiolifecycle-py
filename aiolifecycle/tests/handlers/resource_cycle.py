import json
import logging
import sys
from typing import Any

from aiolifecycle.handlers import init
from aiolifecycle.handlers import sync


def write_json(data: Any) -> None:
    json.dump(data, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


@init(lazy=True)
async def a() -> str:
    await c()
    return "a"


@init(lazy=True)
async def b() -> str:
    await a()
    return "b"


@init(lazy=True)
async def c() -> str:
    await b()
    return "c"


@sync()
async def handler(event, context) -> None:
    try:
        await c()
    except BaseException as err:
        write_json({"exception": f"{type(err).__name__}: {err}"})
    else:
        write_json({"call": {"event": event, "context": context}})
        assert False, "Cycle detection failed"


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    handler({}, {})
