import asyncio.subprocess
import json
import sys
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any
from typing import AsyncIterator
from typing import List

import pytest
import pytest_asyncio


@dataclass
class LambdaCall:
    event: Any
    context: Any


@pytest.fixture
def lambda_calls():
    return [
        LambdaCall(event={"event": 1}, context={"context": 1}),
        LambdaCall(event={"event": 2}, context={"context": 2}),
        LambdaCall(event={"event": 3}, context={"context": 3}),
    ]


@pytest_asyncio.fixture
async def handler_example_proc() -> AsyncIterator[asyncio.subprocess.Process]:
    proc = await asyncio.subprocess.create_subprocess_exec(
        sys.executable, '-m', 'lambda_asyncio.tests.handler_example',
        stdout=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.PIPE,
    )

    try:
        yield proc
    finally:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass


@pytest.mark.asyncio
async def test_handler(
    lambda_calls: List[LambdaCall], handler_example_proc: asyncio.subprocess.Process,
) -> None:
    proc = handler_example_proc

    stdout = proc.stdout
    assert stdout is not None
    stdin = proc.stdin
    assert stdin is not None

    async def get_event() -> Any:
        line = await stdout.readuntil()  # type: ignore
        if not line:
            raise asyncio.CancelledError()

        line = line.strip()
        event = json.loads(line)
        print(event, file=sys.stderr)
        return event

    async def read_start():
        event = await get_event()
        assert event == {"init": 10}

        event = await get_event()
        assert event == {"init": 20}

        for call in lambda_calls:
            event = await get_event()
            assert event['call'] == asdict(call)

    async def read_end():
        event = await get_event()
        assert event == {"close": 20}

        event = await get_event()
        assert event == {"close": 10}

    async def write_calls():
        for call in lambda_calls:
            stdin.write(json.dumps(asdict(call)).encode('utf-8'))
            stdin.write(b"\n")
            await stdin.drain()

        stdin.close()

    r = asyncio.create_task(read_start())
    w = asyncio.create_task(write_calls())
    await asyncio.wait_for(asyncio.gather(r, w), timeout=10)

    proc.terminate()

    await asyncio.wait_for(read_end(), timeout=10)

    assert (await proc.wait()) == 0
