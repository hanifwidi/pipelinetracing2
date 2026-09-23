# utils/benchmark.py
import time
import functools
import tracemalloc
from typing import Callable, Any
from utils.logger import log

def benchmark(func: Callable) -> Callable:
    """
    A decorator that logs the execution time and memory footprint of the 
    decorated function. Essential for tuning performance bottlenecks.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        # Start tracking memory and time
        tracemalloc.start()
        start_time = time.perf_counter()
        
        try:
            result = func(*args, **kwargs)
        finally:
            # Stop tracking
            end_time = time.perf_counter()
            current_mem, peak_mem = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            
            elapsed_time = end_time - start_time
            peak_mem_mb = peak_mem / (1024 * 1024)
            
            log.debug(
                f"[BENCHMARK] {func.__name__} | "
                f"Time: {elapsed_time:.4f}s | "
                f"Peak Mem: {peak_mem_mb:.2f} MB"
            )
            
        return result
    return wrapper