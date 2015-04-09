from functools import partial
import inspect
from multiprocessing import Process, Event, Pipe
from collections import deque
import asyncio
from threading import Thread


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
            proxied_obj = self.proxy_type(*self.proxy_args, **self.proxy_kwargs)
            self.message_pipe.send(True)
        except Exception as e:
            self.message_pipe.send(e)
        while not self.close_event.is_set():
            if not self.message_pipe.poll(timeout=1):
                continue
            # Need to check if close_event is set to prevent broken message pipe errors
            if self.close_event.is_set():
                return self.close()
            func_name, args, kwargs = self.message_pipe.recv()
            try:
                if func_name == '__getattr__':
                    result = getattr(proxied_obj, args[0])
                elif func_name == '__setattr__':
                    result = setattr(proxied_obj, args[0], args[1])
                else:
                    result = getattr(proxied_obj, func_name)(*args, **kwargs)
                self.message_pipe.send(result)
            except Exception as e:
                self.message_pipe.send(e)
        return self.close()

    def close(self):
        self.is_closed_event.set()


class ManagerThread(Thread):
    """
    Polls the message_pipe waiting for messages from the worker and sets the result of futures when received.
    """
    def __init__(self, message_pipe, future_deque, close_event, event_loop):
        super().__init__()
        self.message_pipe = message_pipe
        self.future_deque = future_deque
        self.close_event = close_event
        self.event_loop = event_loop

    def run(self):
        while not self.close_event.is_set():
            if not self.message_pipe.poll(timeout=1):
                continue
            result = self.message_pipe.recv()
            future = self.future_deque.popleft()
            if isinstance(result, Exception):
                if self.event_loop.is_running():
                    self.event_loop.call_soon_threadsafe(future.set_exception, result)
                else:
                    future.set_exception(result)
            else:
                if self.event_loop.is_running():
                    self.event_loop.call_soon_threadsafe(future.set_result, result)
                else:
                    future.set_result(result)


class Manager:
    """
    Creates a Worker and sends tasks to it. Returns and sets futures for the task results.
    When called in the asyncio event_loop, polls Worker results with ManagerThread.
    """

    def __init__(self, proxy_type, args, kwargs, instance_future, event_loop=None):
        self.message_pipe, worker_pipe = Pipe()
        self.future_deque = deque()
        self.future_deque.append(instance_future)
        self.close_event = Event()
        self.worker_closed_event = Event()
        self.event_loop = event_loop if event_loop is not None else asyncio.get_event_loop()
        self.thread = ManagerThread(self.message_pipe, self.future_deque, self.close_event, self.event_loop)
        self.worker = Worker(worker_pipe, self.close_event, self.worker_closed_event, proxy_type, args, kwargs)
        self.worker.start()
        self.thread.start()

    def run_async(self, name, *args, **kwargs):
        future = ProcessFuture()
        try:
            self.message_pipe.send([name, args, kwargs])
            self.future_deque.append(future)
        except Exception as e:
            future.set_exception(e)
        return future

    def close(self, wait=False):
        self.close_event.set()
        if wait:
            self.worker_closed_event.wait()

    def __del__(self):
        self.close()

    @property
    def is_closing(self):
        return self.close_event.is_set()

    @property
    def is_closed(self):
        return self.worker_closed_event.is_set()


class ProcessFuture(asyncio.Future):
    """
    Future whose result is computed from another process and can't be cancelled.
    """
    def cancel(self):
        raise RuntimeError("ProcessFuture instances cannot be cancelled.")


class ProcessInterface(ProcessFuture):
    """
    Interface to proxy_type(*args, **kwargs) running in another process.
    Only an interface to the object's methods, can't set or get member variables.
    """
    _fields = {'proxy_type', 'method_names', '_manager', '_loop', '_callbacks', '_result', '_state', '_log_traceback',
               '_exception'}

    def __init__(self, proxy_type, *args, event_loop=None, **kwargs):
        super().__init__()
        self.method_names = set(self.iter_method_names(proxy_type))
        self.proxy_type = proxy_type
        self._manager = Manager(proxy_type, args, kwargs, self, event_loop=event_loop)

    @classmethod
    def iter_method_names(cls, proxy_type):
        func_or_method = lambda x: inspect.isfunction(x) or inspect.ismethod(x)
        for name, member in inspect.getmembers(proxy_type, predicate=func_or_method):
            yield name

    def __getattr__(self, name):
        if name in self.method_names:
            return partial(self._manager.run_async, name)
        return self._manager.run_async('__getattr__', name)

    def __setattr__(self, name, value):
        if name in self._fields:
            super().__setattr__(name, value)
            return
        return self._manager.run_async('__setattr__', name, value)

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