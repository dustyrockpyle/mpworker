# mpworker

### Basic usage:

```python
from mpworker import ProcessMixin
from time import sleep
from os import getpid
import asyncio


# ProcessMixin exposes a classmethod, spawn 
# spawn creates an instance of the class in another process.
class ExampleClass(ProcessMixin):
    """
    Instances of this class can run in another process, but you define it normally.
    """
    def __init__(self, some_arg, keyword_arg=None, **kwargs):
        # Any synchronized objects form multiprocessing need to be passed in init.
        self.some_arg = some_arg
        self.keyword_arg = keyword_arg
    
    def getpid(self):
        # This will return the pid of the process this instance runs in.
        return getpid()
        
    # Arguments passed to methods are sent through a pipe, and so must be pickleable.
    def get_params(self, *params):
        # Return the passed params.
        # You can call other methods within the class normally.
        self.print_params(params)
        # Returned values must be pickleable.
        return params
        
    def print_params(self, *params):
        print(params)
        
if __name__ == '__main__':
    with ExampleClass.spawn('some_arg', keyword_arg=[1,2,3]) as proxy:
        # proxy is a future, and also the interface to the object in another process
        # proxy.done() will be true after the instance has been initialized
        sleep(1)
        assert proxy.done()
        
        # Methods called off the proxied object return a future that will hold the result
        future_pid = proxy.getpid()
        proxy_pid = asyncio.get_event_loop().run_until_complete(future_pid)
        assert proxy_pid != getpid()
        
        # The methods start running right away; you don't need to use the asyncio event_loop
        params = 1, [2, 3], '4 5'
        future_params = proxy.get_params(*params)
        sleep(1)
        assert params == future_params.result()
        
    # When used in a with statement, the process will close on exiting the context
    # You can always close the process explicity; 
    # with wait=True it will wait until the process closes
    proxy.close(wait=True)
```
