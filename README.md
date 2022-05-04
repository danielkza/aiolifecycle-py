# lambda-asyncio

Safely use asyncio handlers in AWS Lambda functions.

## Installation

Run `pip install lambda-asyncio`, or add it to your package dependencies.

## Usage

### Handler

Define your Lambda handler as an `async` function, and add the `lambda_async_handler`
annotation.

```python
@lambda_async_handler()
async def my_handler(event, context):
    await asyncio.sleep(1)
    return response
```

By default, handlers are *eager*, meaning an event loop will be created and
initialisation functions will be immediately run on module import. This somewhat
matches the behaviour of a synchronous Lambda function with resources as global
module variables.

If you wan to initialise resources only when a handler is first called, do:

```python
@lambda_async_handler(eager=False)
async def my_handler(event, context):
    await asyncio.sleep(1)
    return response
```

### Initialisation

You can define `async` initialization functions to prepare resources for use by
handlers.

These can be simple `async def`s returning nothing:

```python
from lambda_asyncio import lambda_async_init

@lambda_async_init()
async def my_init() -> None:
    print('Hello, world!')
```

Initialization order can be controlled with the `order` parameter:

```python
from lambda_asyncio import lambda_async_init


@lambda_async_init(order=20)
async def world():
    print('World!')

@lambda_async_init(order=10)
async def hello():
    print('Hello!')
```

Or you can use `AsyncContextManagers`, and access the resources they create by
refering to the handler function. Proper lifetime will be managed internally, such
that the initialization will happen once.


```python
import asyncio
from typing import AsyncIterator, Tuple
from asyncio.stream import StreamReader, StreamWriter

import aiofiles
from lambda_asyncio import lambda_async_init, lambda_async_handler

@lambda_async_init()
@asynccontextmanager
async def json_log_file() -> AsyncIterator[]:
    async with aiofiles.open('/tmp/my-file.json', mode='a') as f:
        yield f

@lambda_async_handler()
async def handler(event, context):
    log_file = await json_log_file()
    await log_file.write(json.dumps(event) + ")
    await log_file.
    reader, writer = await connection()
    writer.write('GET / HTTP/1.1\r\n')
    writer.write('Host: google.com\r\n')
    await writer.drain()

    response = await reader.read()
    print(response)
```
