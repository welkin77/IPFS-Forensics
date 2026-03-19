"""
utils/error_handler.py - 精简版
只保留实际被项目使用的部分
"""

import logging
import functools
import time
import asyncio
from typing import Callable

logger = logging.getLogger(__name__)


def retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """同步重试装饰器 - 被 crawler.py 和 gateway_monitor.py 使用"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(f"{func.__name__} 重试 {max_retries} 次后失败: {e}")
                        raise
                    logger.warning(f"{func.__name__} 第{attempt+1}次失败, {current_delay:.1f}s后重试")
                    time.sleep(current_delay)
                    current_delay = min(current_delay * backoff, 60)
        return wrapper
    return decorator


def async_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """异步重试装饰器 - 被 dht_probe.py 使用"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        raise
                    await asyncio.sleep(current_delay)
                    current_delay = min(current_delay * backoff, 60)
        return wrapper
    return decorator