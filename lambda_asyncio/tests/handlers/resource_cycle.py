import json
import logging
import sys
from typing import Any

from lambda_asyncio.handlers import lambda_async_handler
from lambda_asyncio.handlers import lambda_async_init


def write_json(data: Any) -> None:
    json.dump(data, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


@lambda_async_init()
async def a() -> str:
    await c()
    return "a"


@lambda_async_init()
async def b() -> str:
    await a()
    return "b"


@lambda_async_init()
async def c() -> str:
    await b()
    return "c"


@lambda_async_handler()
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
