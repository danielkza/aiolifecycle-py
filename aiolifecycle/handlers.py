from __future__ import annotations

import asyncio.events
import asyncio.runners
import concurrent.futures
import logging
import signal
import sys
import threading
import weakref
from asyncio.unix_events import SelectorEventLoop
from collections import defaultdict
from contextlib import asynccontextmanager
from contextlib import AsyncExitStack
from contextvars import ContextVar
from functools import wraps
from threading import Thread
from typing import Any
from typing import AsyncContextManager
from typing import Awaitable
from typing import Callable
from typing import cast
from typing import List
from typing import MutableMapping
from typing import Optional
from typing import overload
from typing import Tuple
from typing import TypeVar
from typing import Union

from typing_extensions import Protocol

from .exceptions import InitHandlerCycleException


T = TypeVar("T")
Response = TypeVar("Response")
InitCallback = Union[
    Callable[[], AsyncContextManager[Any]],
    Callable[[], Awaitable[Any]],
]

_init_callbacks: MutableMapping[int, List[InitCallback]] = defaultdict(list)
_log = logging.getLogger(__name__)

aiolifecycle_init_chain: ContextVar[Tuple[Any, ...]] = ContextVar(
    'aiolifecycle_init_chain', default=(),
)


def wrap_sig_handler(f, *fargs, **fkwargs):
    @wraps(f)
    def handler(sig, *_):
        _log.warning(f'Got signal {sig}')

        return f(*fargs, **fkwargs)

    return handler


def wait_thread(thread_ref: weakref.ReferenceType[Thread]):
    # Wait until our loop finishes before allowing Python to shutdown threads
    thread = thread_ref()
    if not thread:
        return

    thread.join()


class EventLoop(SelectorEventLoop):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.__term_event = self.create_future()
        self.__exit_stack = AsyncExitStack()

    async def __aclose(self) -> None:
        _log.debug('Waiting for cleanup')
        try:
            await self.__exit_stack.aclose()
            self.__term_event.set_result(0)
        except Exception:
            _log.exception("Failure cleaning up async resources")
        finally:
            if not self.__term_event.done():
                self.__term_event.set_result(1)

    def _close(self, sig: Optional[int] = None) -> None:
        if self.__term_event.done():
            return

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, signal.SIG_DFL)

        signal.set_wakeup_fd(-1)

        if not self.is_running():
            self.run_until_complete(self.__aclose())
        else:
            fut = asyncio.run_coroutine_threadsafe(self.__aclose(), loop=self)
            fut.result()

    def __thread(self) -> None:
        asyncio.set_event_loop(self)

        try:
            self.run_until_complete(self.__term_event)
        except Exception:
            _log.exception('Completed with exception')
        finally:
            _log.debug('Cancelling all tasks')
            asyncio.runners._cancel_all_tasks(self)  # type: ignore

            _log.debug('Shutting down asyncgens')
            self.run_until_complete(self.shutdown_asyncgens())

            if sys.version_info >= (3, 9):
                _log.debug('Shutting down executors')
                self.run_until_complete(self.shutdown_default_executor())

            _log.debug('Shut down')
            self.close()

            asyncio.events.set_event_loop(None)

    def run_in_background_thread(self) -> None:
        # We can't use loop.add_signal_handler because it schedules the callback
        # in the loop itself. It will run in the background thread, which then
        # can't make any other signal changes, and hence can't remove the signal
        # handlers

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, wrap_sig_handler(self._close, sig))

        # We are threading a bit dangerously into internals here
        csock = self._csock  # type: ignore
        if csock:
            signal.set_wakeup_fd(csock.fileno())

        t = Thread(target=self.__thread)
        t.start()

    @overload
    async def with_resource(self, cm: Callable[[], Awaitable[T]]) -> T:
        pass

    @overload
    async def with_resource(self, cm: Callable[[], AsyncContextManager[T]]) -> T:
        pass

    async def with_resource(self, cm: InitCallback):
        coro = cm()
        if hasattr(coro, '__aexit__'):
            coro = cast(AsyncContextManager[Any], coro)
            value = await self.__exit_stack.enter_async_context(coro)
        else:
            # Define a dummy context manager to keep the resource alive
            @asynccontextmanager
            async def resource():
                yield (await coro)

            value = await self.__exit_stack.enter_async_context(resource())

        return value


async def run_init_callbacks(loop: EventLoop) -> None:
    for _, callbacks in sorted(_init_callbacks.items()):
        for callback in callbacks:
            await loop.with_resource(callback)


_loop: Optional[EventLoop] = None
_loop_lock = threading.RLock()
_loop_init: Optional[concurrent.futures.Future] = None


def get_loop() -> EventLoop:
    loop = asyncio.events._get_running_loop()
    if loop:
        assert isinstance(loop, EventLoop)
        return loop

    global _loop, _loop_lock, _loop_init

    with _loop_lock:
        try:
            if _loop is None:
                _loop = EventLoop()
                _loop.run_in_background_thread()
                _loop_init = asyncio.run_coroutine_threadsafe(
                    run_init_callbacks(_loop), loop=_loop,
                )
        except BaseException:
            if _loop is not None:
                if _loop_init and not _loop_init.done():
                    _loop_init.cancel()

                _loop._close()
                _loop = None

            raise

    assert _loop_init
    try:
        _loop_init.result()
    except BaseException:
        # Repeat the cleanup separately because we need to release the lock
        # to grab the result, but take it again here

        with _loop_lock:
            _loop._close()
            _loop = None
            _loop_init = None

        raise

    return _loop


AsyncHandler = Callable[..., Awaitable[Response]]
SyncHandler = Callable[..., Response]


class AsyncHandlerDecorator(Protocol):
    def __call__(self, f: AsyncHandler) -> SyncHandler:
        pass


def sync(*, eager: bool = True) -> AsyncHandlerDecorator:
    def decorate(f: AsyncHandler) -> SyncHandler:
        @wraps(f)
        def handler(*args, **kwargs) -> Response:
            # kill the whole program if an init fails
            loop = get_loop()

            try:
                fut = asyncio.run_coroutine_threadsafe(f(*args, **kwargs), loop=loop)
                return fut.result()
            except BaseException:
                loop._close()
                raise

        if eager:
            get_loop()

        return handler

    return decorate


class SyncInitDecorator(Protocol):
    @overload
    def __call__(
        self, cm: Callable[[], AsyncContextManager[T]],
    ) -> Callable[[], Awaitable[T]]:
        pass

    @overload
    def __call__(
        self, f: Callable[[], Awaitable[T]],
    ) -> Callable[[], Awaitable[T]]:
        pass


def init(*, order: Optional[int] = None, lazy: bool = False) -> SyncInitDecorator:
    if order is not None and lazy:
        raise ValueError("Can't specify order for lazy init")

    def decorate(cm):
        # These callbacks will actually be schedule in a separate thread, as thats
        # how our loop runs. To avoid conflicting initialisations we need some form
        # of synchronization when doing the result caching. We do this by taking
        # a lock in the synchronous part of the call, spinning up a coroutine in
        # the background if we haven't initialised yet, and returning the corresponding
        # future.
        # If initialisation has already taken place, we will just get the existing result
        # in the future.

        lock = threading.Lock()
        result_fut: Optional[concurrent.futures.Future] = None

        @wraps(cm)
        def sync_wrapper():
            chain = aiolifecycle_init_chain.get()
            if sync_wrapper in chain:
                raise InitHandlerCycleException(chain + (sync_wrapper,))

            reset_chain = aiolifecycle_init_chain.set(chain + (sync_wrapper,))
            try:
                loop = get_loop()

                with lock:
                    nonlocal result_fut
                    if not result_fut:
                        result_fut = asyncio.run_coroutine_threadsafe(
                            loop.with_resource(cm), loop=loop,
                        )

                return asyncio.wrap_future(result_fut, loop=loop)
            finally:
                aiolifecycle_init_chain.reset(reset_chain)

        if not lazy:
            real_order = order or 2 ** 32 - 1

            global _init_callbacks
            _init_callbacks[real_order].append(sync_wrapper)

        return sync_wrapper

    return decorate
