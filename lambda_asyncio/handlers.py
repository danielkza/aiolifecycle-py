from __future__ import annotations

import asyncio.events
import asyncio.runners
import logging
import os
import signal
import sys
from asyncio import AbstractEventLoop
from asyncio.futures import Future
from collections import defaultdict
from contextlib import AsyncExitStack
from functools import partial
from functools import wraps
from threading import Thread
from typing import Any
from typing import AsyncContextManager
from typing import Awaitable
from typing import Callable
from typing import List
from typing import MutableMapping
from typing import Optional
from typing import overload
from typing import TypeVar

from typing_extensions import Protocol

T = TypeVar("T")
Response = TypeVar("Response")
InitCallback = AsyncContextManager[Any]

_loop: Optional[AbstractEventLoop] = None
_init_callbacks: MutableMapping[int, List[InitCallback]] = defaultdict(list)
_log = logging.getLogger(__name__)


def run_init_callbacks(
    loop: AbstractEventLoop, exit_stack: AsyncExitStack,
) -> None:
    async def run_callbacks():
        try:
            for order, callbacks in sorted(_init_callbacks.items()):
                for callback in callbacks:
                    _log.info(f"Running init callback: {order}, {callback}")

                    coro = callback()

                    if hasattr(coro, '__aexit__'):
                        await exit_stack.enter_async_context(coro)
                    else:
                        await coro
        except:  #
            await exit_stack.aclose()
            raise

        return exit_stack

    fut = asyncio.run_coroutine_threadsafe(run_callbacks(), loop=loop)
    return fut.result()


def start_background_loop(
    loop: AbstractEventLoop, term_event: Future[None],
) -> None:
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(term_event)
    except Exception:
        _log.exception('Completed with exception')
        sys.exit(1)
    finally:
        try:
            _log.debug('Cancelling all tasks')
            asyncio.runners._cancel_all_tasks(loop)  # type: ignore

            _log.debug('Shutting down asyncgens')
            loop.run_until_complete(loop.shutdown_asyncgens())

            _log.debug('Shutting down executors')
            loop.run_until_complete(loop.shutdown_default_executor())

            _log.debug('Shut down')
            asyncio.events.set_event_loop(None)
        except Exception:
            os._exit(1)

    os._exit(0)


def terminate(
    loop: AbstractEventLoop, term_event: Future[None], exit_stack: AsyncExitStack,
    sig: int, _: Any,
) -> None:
    _log.warning(f'Got signal {sig}')

    if not term_event.done():
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

        f = asyncio.run_coroutine_threadsafe(exit_stack.aclose(), loop=loop)
        try:
            _log.debug('Waiting for cleanup')
            f.result()
        except Exception:
            _log.exception("Failure cleaning up async inits")
        finally:
            loop.call_soon_threadsafe(term_event.set_result, None)


def get_loop() -> AbstractEventLoop:
    global _loop
    if _loop is not None:
        return _loop

    loop = asyncio.events.new_event_loop()
    term_event = loop.create_future()

    exit_stack = AsyncExitStack()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, partial(terminate, loop, term_event, exit_stack))

    t = Thread(target=start_background_loop, args=(loop, term_event))
    t.start()

    run_init_callbacks(loop, exit_stack)
    _loop = loop
    return loop


LambdaAsyncHandler = Callable[..., Awaitable[Response]]
LambdaHandler = Callable[..., Response]


class LambdaAsyncHandlerDecorator(Protocol):
    def __call__(self, f: LambdaAsyncHandler) -> LambdaHandler:
        pass


def lambda_async_handler(*, eager: bool = True) -> LambdaAsyncHandlerDecorator:
    def decorate(f: LambdaAsyncHandler) -> LambdaHandler:
        @wraps(f)
        def handler(*args, **kwargs) -> Response:
            loop = get_loop()

            fut = asyncio.run_coroutine_threadsafe(f(*args, **kwargs), loop=loop)
            return fut.result()

        if eager:
            get_loop()

        return handler

    return decorate


class LambdaAsyncInitDecorator(Protocol):
    @overload
    def __call__(
        self, cm: Callable[[], AsyncContextManager[T]],
    ) -> Callable[[], AsyncContextManager[T]]:
        pass

    @overload
    def __call__(
        self, f: Callable[..., Awaitable[None]],
    ) -> Callable[..., Awaitable[None]]:
        pass


def lambda_async_init(*, order: int = 50) -> LambdaAsyncInitDecorator:
    def decorate(cm):
        global _init_callbacks
        _init_callbacks[order].append(cm)

        return cm

    return decorate
