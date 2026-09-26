import functools
import time
from utils.logger import log

def benchmark(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            log.debug("[BENCHMARK] %s | %.4fs", func.__name__, time.perf_counter() - start)
    return wrapper
