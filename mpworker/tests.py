from mpworker import ProcessMixin
import os
import asyncio
from time import sleep
from multiprocessing import Value
import unittest
from math import factorial
run = asyncio.get_event_loop().run_until_complete


class ExampleClass(ProcessMixin):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def sleep(self):
        sleep(.1)

    def getpid(self):
        return os.getpid()

    def get_init_args(self):
        return self.args

    def get_init_kwargs(self):
        return self.kwargs

    def get_args(self, *args, **kwargs):
        return args

    def get_kwargs(self, *args, **kwargs):
        return kwargs

    def raise_assertion_error(self):
        raise AssertionError()

    def get_arg(self, arg):
        return arg

    def get_unpickleable(self):
        return Value('i', 0)

    def absurd_factorial(self, n):
        if n == 1:
            return 1
        with ExampleClass.spawn() as e:
            return run(e.absurd_factorial(n-1)) * n


class TestMixin(unittest.TestCase):
    def setUp(self):
        self.args = (1, 'string', list(range(5)), {1: 1, 2: 2, 3: 3})
        self.kwargs = {'one': '1', 'two': 2}
        self.proxy = ExampleClass.spawn(*self.args, **self.kwargs)
        run(self.proxy)

    def tearDown(self):
        self.proxy.close()

    def test_interface_done(self):
        self.assertTrue(self.proxy.done())

    def test_call(self):
        future = self.proxy.sleep()
        self.assertIsInstance(future, asyncio.Future)
        self.assertFalse(future.done())
        run(future)
        self.assertTrue(future.done())

    def test_managed_future(self):
        future = self.proxy.sleep()
        self.assertFalse(future.done())
        sleep(1)
        self.assertTrue(future.done())

    def test_pid(self):
        self.assertNotEqual(os.getpid(), run(self.proxy.getpid()))

    def test_init_args(self):
        self.assertEqual(self.args, run(self.proxy.get_init_args()))

    def test_init_kwargs(self):
        self.assertEqual(self.kwargs, run(self.proxy.get_init_kwargs()))

    def test_passed_args(self):
        self.assertEquals(self.args, run(self.proxy.get_args(*self.args, **self.kwargs)))

    def test_passed_kwargs(self):
        self.assertEqual(self.kwargs, run(self.proxy.get_kwargs(*self.args, **self.kwargs)))

    def test_exception(self):
        self.assertRaises(AssertionError, run, self.proxy.raise_assertion_error())

    def test_multiple_calls(self):
        future = asyncio.gather(*list(map(self.proxy.get_arg, range(10))))
        result = run(future)
        self.assertEqual(result, list(range(10)))

    def test_with_close(self):
        self.assertFalse(self.proxy.is_closing)
        with self.proxy as e:
            pass
        self.assertTrue(self.proxy.is_closing)

    def test_close(self):
        self.assertFalse(self.proxy.is_closing)
        self.proxy.close()
        self.assertTrue(self.proxy.is_closing)
        self.assertFalse(self.proxy.is_closed)
        self.proxy.close(True)
        self.assertTrue(self.proxy.is_closed)

    def test_return_unpickleable(self):
        self.assertRaises(RuntimeError, run, self.proxy.get_unpickleable())

    def test_send_unpickleable(self):
        self.assertRaises(RuntimeError, run, self.proxy.get_arg(Value('i', 0)))

    def test_absurd_factorial(self):
        self.assertEqual(factorial(4), run(self.proxy.absurd_factorial(4)))


class ExampleShared(ProcessMixin):
    def __init__(self, shared):
        self.shared = shared

    def set_value(self, value):
        self.shared.value = value


class TestSharedMemory(unittest.TestCase):
    def setUp(self):
        self.shared = Value('i', 0)
        self.proxy = ExampleShared.spawn(self.shared)

    def tearDown(self):
        self.proxy.close()

    def test_set(self):
        self.assertEqual(0, self.shared.value)
        run(self.proxy.set_value(5))
        self.assertEqual(5, self.shared.value)


class ExampleFailInit(ProcessMixin):
    def __init__(self):
        raise AssertionError()

    def test(self):
        return True


class TestFailInit(unittest.TestCase):
    def test_init(self):
        with ExampleFailInit.spawn() as proxy:
            self.assertRaises(AssertionError, run, proxy)

    def test_call(self):
        with ExampleFailInit.spawn() as proxy:
            self.assertRaises(UnboundLocalError, run, proxy.test())
            self.assertRaises(AssertionError, run, proxy)


class ExampleMethodNames(ProcessMixin):
    def __init__(self):
        self.value = 'value'
        super().__init__()

    def test1(self):
        pass

    def test2(self):
        pass

    @property
    def test3(self):
        return 3


class TestMethodNames(unittest.TestCase):
    def setUp(self):
        self.proxy = ExampleMethodNames.spawn()

    def tearDown(self):
        self.proxy.close()

    def test_method_names(self):
        self.assertSetEqual(self.proxy.method_names, {'__init__', 'test1', 'test2'})

    def test_getter(self):
        self.assertEqual(run(self.proxy.value), 'value')

    def test_setter(self):
        self.proxy.value2 = 'value2'
        self.assertEqual(run(self.proxy.value2), 'value2')