# aiolifecycle

Safely use asyncio handlers in synchronous context.

## Use case

If you want to run an asyncio-based program in a synchronous context - such as
a command line invocation - you can use `asyncio.run` from the standard library.
But it immediately spins up and terminates an event loop. What if you want to a
continuous workflow, where you can initialise and re-use resources?

The original need for this project arose when adapting an asyncio-based system
to AWS Lambda, which makes multiple synchronous function calls in the same
interpreter environment.

## Installation

Run `pip install aiolifecycle`, or add it to your package dependencies.

## Usage

### Handler

Define your handler as an `async` function, and add the `sync` annotation. Then
it can safely be called synchronously. An event loop will automatically be
initialised with its associated resources.


```python
import asyncio

from aiolifecycle import sync


@sync()
async def my_handler() -> None:
    await asyncio.sleep(1)
```

By default, handlers are *eager*, meaning an event loop will be created and
initialisation functions will be immediately run on module import.

If you want to initialise resources only when a handler is first called, do:

```python
import asyncio

from aiolifecycle import sync


@sync(eager=False)
async def my_handler() -> None:
    await asyncio.sleep(1)
```

### Initialisation

You can define `async` initialisation functions to prepare resources for use by
handlers. These can be simple `async def`s returning nothing.

In the following example, `my_init` will be called exactly once, before any handlers
run.

```python
import asyncio

from aiolifecycle import sync, init


@init
async def my_init() -> None:
    print('Hello, world!')


@sync
async def my_handler() -> None:
    await asyncio.sleep(1)
```

Initialisation order can be controlled with the `order` parameter. In the following
example, `hello` will be called before `world`. Functions with the same order (or
undefined order) are called in the order they were defined.

```python
import asyncio

from aiolifecycle import sync, init

@init(order=20)
async def world() -> None:
    print('World!')


@init(order=10)
async def hello() -> None:
    print('Hello!')


@sync()
async def my_handler() -> None:
    await asyncio.sleep(1)

```

Initialisation functions can manage resources. You can simply return the resource
from an `init` function (if no finalisation is necessary), or define it as an
`asynccontextmanager`

Or you can use `AsyncContextManagers`, and access the resources they create by
refering to the handler function. Proper lifetime will be managed internally, such
that the initialisation will happen once.

```python
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiofiles
from aiofiles.threadpool.text import AsyncTextIOWrapper

from aiolifecycle import sync
from aiolifecycle import init


@init
async def json_log_path() -> str:
    # Run complicated logic to determine path, only once!
    # ....
    return '/tmp/my-file.json'


@init()
@asynccontextmanager
async def json_log_file() -> AsyncIterator[AsyncTextIOWrapper]:
    log_path = await json_log_path()
    # File will be open before any handler is called, and cleaned up on shutdown
    async with aiofiles.open(log_path, mode='a') as f:
        yield f


@sync()
async def handler():
    log_file = await json_log_file()
    await log_file.write(json.dumps(event) + "\n")
    await log_file.flush()
```
