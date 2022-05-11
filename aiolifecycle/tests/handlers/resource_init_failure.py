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
async def fail() -> str:
    raise RuntimeError("Init failed")


@sync(eager=False)
async def handler() -> None:
    await fail()
    assert False, "Should not reach"


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    handler()
