# aiolifecycle

Safely use asyncio handlers in AWS Lambda functions.

## Installation

Run `pip install aiolifecycle`, or add it to your package dependencies.

## Usage

### Handler

Define your Lambda handler as an `async` function, and add the `lambda_async_handler`
annotation.

```python

```

By default, handlers are *eager*, meaning an event loop will be created and
initialisation functions will be immediately run on module import. This somewhat
matches the behaviour of a synchronous Lambda function with resources as global
module variables.

If you wan to initialise resources only when a handler is first called, do:

```python

```

### Initialisation

You can define `async` initialization functions to prepare resources for use by
handlers.

These can be simple `async def`s returning nothing:

```python
from aiolifecycle import lambda_async_init


```

Initialization order can be controlled with the `order` parameter:

```python

```

Or you can use `AsyncContextManagers`, and access the resources they create by
refering to the handler function. Proper lifetime will be managed internally, such
that the initialization will happen once.


```python

```
