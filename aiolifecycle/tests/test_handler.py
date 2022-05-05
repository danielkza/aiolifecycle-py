import asyncio.subprocess
import json
import sys
from asyncio import IncompleteReadError
from asyncio import StreamReader
from asyncio import StreamWriter
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any
from typing import AsyncIterator
from typing import Iterable
from typing import List
from typing import TextIO

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
async def handler_proc(
    request: pytest.FixtureRequest,
) -> AsyncIterator[asyncio.subprocess.Process]:
    parent_module, _ = __name__.rsplit('.', 1)

    # error: "FixtureRequest" has no attribute "param"
    # due to missing pytest types
    handler_module = \
        f"{parent_module}.handlers.{request.param}"  # type: ignore

    proc = await asyncio.subprocess.create_subprocess_exec(
        sys.executable, '-m', handler_module,
        stdout=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        yield proc
    finally:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass


async def get_event(stdout: StreamReader) -> Any:
    try:
        line = await stdout.readuntil()
    except IncompleteReadError as err:
        line = err.partial

    if not line:
        raise asyncio.CancelledError()

    line = line.strip()
    print(line, file=sys.stderr)

    event = json.loads(line)

    return event


async def check_events(events: Iterable[Any], stdout: StreamReader) -> None:
    for i, event in enumerate(events):
        assert (await get_event(stdout)) == event, f"Event {i} doesn't match"


async def check_calls(calls: Iterable[LambdaCall], stdout: StreamReader) -> None:
    await check_events([{'call': asdict(call)} for call in calls], stdout)


async def write_calls(lambda_calls: Iterable[LambdaCall], stdin: StreamWriter) -> None:
    for call in lambda_calls:
        stdin.write(json.dumps(asdict(call)).encode('utf-8'))
        stdin.write(b"\n")
        await stdin.drain()

    stdin.close()


async def pipe_to_file(reader: StreamReader, out: TextIO) -> None:
    loop = asyncio.get_event_loop()
    async for line in reader:
        await loop.run_in_executor(
            None, out.write, line.decode('utf-8'),
        )


@pytest.mark.parametrize("handler_proc", ["basic_order"], indirect=True)
@pytest.mark.asyncio
async def test_handler_basic(
    lambda_calls: List[LambdaCall], handler_proc: asyncio.subprocess.Process,
) -> None:
    proc = handler_proc

    stdout = proc.stdout
    assert stdout is not None
    stderr = proc.stderr
    assert stderr is not None
    stdin = proc.stdin
    assert stdin is not None

    start_events = [
        {"init": 10},
        {"init": 20},
    ]
    end_events = [
        {"close": 20},
        {"close": 10},
    ]

    async def read():
        await check_events(start_events, stdout)
        await check_calls(lambda_calls, stdout)

    r_out = asyncio.create_task(read())
    r_err = asyncio.create_task(pipe_to_file(stderr, sys.stderr))
    w = asyncio.create_task(write_calls(lambda_calls, stdin))
    await asyncio.wait_for(asyncio.gather(r_out, w), timeout=10)

    proc.terminate()

    await asyncio.wait_for(check_events(end_events, stdout), timeout=10)
    await r_err

    assert (await proc.wait()) == 0


@pytest.mark.parametrize("handler_proc", ["resource_chaining"], indirect=True)
@pytest.mark.asyncio
async def test_handler_resource_chaining(
    lambda_calls: List[LambdaCall], handler_proc: asyncio.subprocess.Process,
) -> None:
    proc = handler_proc

    stdout = proc.stdout
    assert stdout is not None
    stderr = proc.stderr
    assert stderr is not None
    stdin = proc.stdin
    assert stdin is not None

    start_events = [
        {"init": 10},
        {"init": 20},
        {"init": 30},
    ]

    end_events = [
        {"close": 10},
    ]

    async def read():
        await check_events(start_events, stdout)

        for call in lambda_calls:
            await check_events([{"value": 30}], stdout)
            await check_calls([call], stdout)

    r_out = asyncio.create_task(read())
    r_err = asyncio.create_task(pipe_to_file(stderr, sys.stderr))
    w = asyncio.create_task(write_calls(lambda_calls, stdin))
    await asyncio.wait_for(asyncio.gather(r_out, w), timeout=10)

    proc.terminate()

    await asyncio.wait_for(check_events(end_events, stdout), timeout=10)
    await r_err

    assert (await proc.wait()) == 0


@pytest.mark.parametrize("handler_proc", ["resource_cycle"], indirect=True)
@pytest.mark.asyncio
async def test_handler_resource_cycle(
    handler_proc: asyncio.subprocess.Process,
) -> None:
    proc = handler_proc

    stdout = proc.stdout
    assert stdout is not None
    stderr = proc.stderr
    assert stderr is not None
    stdin = proc.stdin
    assert stdin is not None

    run = asyncio.create_task(get_event(stdout))
    r_err = asyncio.create_task(pipe_to_file(stderr, sys.stderr))
    await asyncio.wait_for(run, timeout=10)

    proc.terminate()
    await r_err

    await proc.wait()

    event = run.result()
    assert "exception" in event
    assert "InitHandlerCycleException" in event["exception"]
    assert "Cycle detected" in event["exception"]
