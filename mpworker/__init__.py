from functools import partial
from multiprocessing import Process, Event, Pipe
from collections import deque
import asyncio


class Worker(Process):
    """
    Starts a new process and inits an instance of proxy_type.
    Calls methods and returns results communicated over the message_pipe
    """
    def __init__(self, message_pipe, close_event, is_closed_event, proxy_type, proxy_args, proxy_kwargs):
        super().__init__()
        self.message_pipe = message_pipe
        self.close_event = close_event
        self.is_closed_event = is_closed_event
        self.proxy_type = proxy_type
        self.proxy_args = proxy_args
        self.proxy_kwargs = proxy_kwargs

    def run(self):
        try:
            proxy = self.proxy_type(*self.proxy_args, **self.proxy_kwargs)
        except Exception as e:
            self.message_pipe.send(e)
            return self.close()
        self.message_pipe.send(True)
        while not self.close_event.is_set():
            if not self.message_pipe.poll(timeout=1):
                continue
            func_name, args, kwargs = self.message_pipe.recv()
            try:
                result = getattr(proxy, func_name)(*args, **kwargs)
                self.message_pipe.send(result)
            except Exception as e:
                self.message_pipe.send(e)
        return self.close()

    def close(self):
        self.is_closed_event.set()


class Manager:
    """
    Creates a Worker and sends tasks to it. Returns and sets futures for the task results.
    When called in the asyncio event_loop, polls Worker results on a delay of sleep_time (default is 1 ms).
    """
    sleep_time = .001

    def __init__(self, proxy_type, args, kwargs, instance_future, event_loop=None):
        self.message_pipe, worker_pipe = Pipe()
        self.future_deque = deque()
        self.future_deque.append(instance_future)
        self.close_event = Event()
        self.is_closed_event = Event()
        self.worker = Worker(worker_pipe, self.close_event, self.is_closed_event, proxy_type, args, kwargs)
        self.worker.start()
        self.event_loop = event_loop if event_loop is not None else asyncio.get_event_loop()
        self.event_loop.call_soon(self.process_message_pipe)

    def process_message_pipe(self):
        while self.message_pipe.poll():
            result = self.message_pipe.recv()
            future = self.future_deque.popleft()
            if isinstance(result, Exception):
                future.set_exception(result)
            else:
                future.set_result(result)
        self.event_loop.call_later(self.sleep_time, self.process_message_pipe)

    def run_async(self, name, *args, **kwargs):
        future = ManagedFuture(self)
        try:
            self.message_pipe.send([name, args, kwargs])
            self.future_deque.append(future)
        except Exception as e:
            future.set_exception(e)
        return future

    def close(self, wait=False):
        self.close_event.set()
        if wait:
            self.is_closed_event.wait()

    def __del__(self):
        self.close()

    @property
    def is_closing(self):
        return self.close_event.is_set()

    @property
    def is_closed(self):
        return self.is_closed_event.is_set()


class ManagedFuture(asyncio.Future):
    """
    Future whose result will be set by the given manager.
    """
    def __init__(self, manager):
        self._manager = manager
        super().__init__()

    def _run_manager(self):
        if not super().done():
            self._manager.process_message_pipe()

    def done(self):
        self._run_manager()
        return super().done()

    def result(self):
        self._run_manager()
        return super().result()

    def exception(self):
        self._run_manager()
        return super().exception()

    def cancel(self):
        raise RuntimeError("ManagedFuture instances cannot be cancelled.")


class ProcessInterface(ManagedFuture):
    """
    Interface to proxy_type(*args, **kwargs) running in another process.
    Only an interface to the object's methods, can't set or get member variables.
    """
    def __init__(self, proxy_type, *args, event_loop=None, **kwargs):
        self.proxy_type = proxy_type
        super().__init__(Manager(proxy_type, args, kwargs, self, event_loop=event_loop))

    def __getattr__(self, name):
        return partial(self._manager.run_async, name)

    def set_result(self, result):
        super().set_result(self)

    def close(self, wait=False):
        return self._manager.close(wait)

    def __repr__(self):
        return "{}({})<{}>".format(self.__class__.__name__, repr(self.proxy_type), self._state)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def is_closing(self):
        return self._manager.is_closing

    @property
    def is_closed(self):
        return self._manager.is_closed


class ProcessMixin(object):
    """
    Mixin that provides a spawn classmethod.
    Spawned objects run in another process, and spawn returns an interface to that object.
    """
    @classmethod
    def spawn(cls, *args, event_loop=None, **kwargs):
        return ProcessInterface(cls, *args, event_loop=event_loop, **kwargs)