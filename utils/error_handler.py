"""
全局错误处理模块
位置: utils/error_handler.py

功能：统一异常体系、重试装饰器、熔断器、全局追踪
与现有 utils/ 下的 merkle_tree.py, logger.py 并列
"""

import asyncio
import functools
import logging
import time
import traceback
from datetime import datetime
from typing import Callable, Dict, List, Optional, TypeVar
from dataclasses import dataclass, field
from collections import Counter
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


# ==================== 自定义异常体系 ====================

class ForensicsBaseError(Exception):
    """取证系统基础异常"""

    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code or 'UNKNOWN_ERROR'
        self.details = details or {}
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            'error': True,
            'code': self.code,
            'message': self.message,
            'details': self.details,
            'timestamp': self.timestamp
        }


class IPFSConnectionError(ForensicsBaseError):
    def __init__(self, message="无法连接IPFS节点", **kw):
        super().__init__(message, code='IPFS_CONNECTION_ERROR', **kw)


class IPFSTimeoutError(ForensicsBaseError):
    def __init__(self, message="IPFS操作超时", **kw):
        super().__init__(message, code='IPFS_TIMEOUT', **kw)


class GatewayError(ForensicsBaseError):
    def __init__(self, message: str, gateway: str = None, **kw):
        details = kw.pop('details', {})
        details['gateway'] = gateway
        super().__init__(message, code='GATEWAY_ERROR', details=details, **kw)


class CIDNotFoundError(ForensicsBaseError):
    def __init__(self, cid: str, **kw):
        super().__init__(
            f"CID内容未找到: {cid}",
            code='CID_NOT_FOUND',
            details={'cid': cid}, **kw
        )


class EvidenceIntegrityError(ForensicsBaseError):
    def __init__(self, message: str, evidence_id: str = None, **kw):
        details = kw.pop('details', {})
        details['evidence_id'] = evidence_id
        super().__init__(
            message, code='EVIDENCE_INTEGRITY_ERROR',
            details=details, **kw
        )


class HashMismatchError(EvidenceIntegrityError):
    def __init__(
        self, expected: str, actual: str,
        algorithm: str = 'sha256', **kw
    ):
        super().__init__(
            f"哈希不匹配 ({algorithm}): "
            f"期望 {expected[:16]}..., 实际 {actual[:16]}...",
            details={
                'algorithm': algorithm,
                'expected': expected,
                'actual': actual
            }, **kw
        )


class RateLimitError(ForensicsBaseError):
    def __init__(self, service: str, retry_after: int = None, **kw):
        super().__init__(
            f"{service} 速率限制",
            code='RATE_LIMIT',
            details={'service': service, 'retry_after': retry_after}, **kw
        )


class ConfigurationError(ForensicsBaseError):
    def __init__(self, message: str, **kw):
        super().__init__(message, code='CONFIG_ERROR', **kw)


class MonitorError(ForensicsBaseError):
    def __init__(self, monitor_name: str, message: str, **kw):
        super().__init__(
            f"[{monitor_name}] {message}",
            code='MONITOR_ERROR',
            details={'monitor': monitor_name}, **kw
        )


# ==================== 错误追踪 ====================

class ErrorSeverity(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorRecord:
    error_type: str
    message: str
    severity: ErrorSeverity
    timestamp: datetime = field(default_factory=datetime.utcnow)
    module: str = ""
    function: str = ""
    traceback_str: str = ""
    context: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'error_type': self.error_type,
            'message': self.message,
            'severity': self.severity.value,
            'timestamp': self.timestamp.isoformat(),
            'module': self.module,
            'function': self.function,
            'traceback': self.traceback_str[:2000],
            'context': self.context
        }


class ErrorTracker:
    """全局错误追踪器（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.errors: List[ErrorRecord] = []
        self.max_records = 10000
        self._callbacks: List[Callable] = []

    def record(
        self,
        error: Exception,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        module: str = "",
        function: str = "",
        context: Dict = None
    ):
        record = ErrorRecord(
            error_type=type(error).__name__,
            message=str(error),
            severity=severity,
            module=module,
            function=function,
            traceback_str=traceback.format_exc(),
            context=context or {}
        )
        self.errors.append(record)
        if len(self.errors) > self.max_records:
            self.errors = self.errors[-self.max_records:]

        log_method = getattr(logger, severity.value, logger.error)
        log_method(f"[{module}.{function}] {type(error).__name__}: {error}")

        for cb in self._callbacks:
            try:
                cb(record)
            except Exception:
                pass

    def on_error(self, callback: Callable):
        self._callbacks.append(callback)

    def get_recent(self, limit: int = 50) -> List[dict]:
        return [e.to_dict() for e in self.errors[-limit:]]

    def get_stats(self) -> dict:
        severity_counts = Counter(e.severity.value for e in self.errors)
        type_counts = Counter(e.error_type for e in self.errors)
        module_counts = Counter(e.module for e in self.errors)
        return {
            'total': len(self.errors),
            'by_severity': dict(severity_counts),
            'top_types': dict(type_counts.most_common(10)),
            'top_modules': dict(module_counts.most_common(10)),
            'error_rate_1h': sum(
                1 for e in self.errors
                if (datetime.utcnow() - e.timestamp).total_seconds() < 3600
            )
        }

    def clear(self):
        self.errors.clear()


# 全局实例
error_tracker = ErrorTracker()


# ==================== 重试装饰器 ====================

def retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable = None
):
    """同步重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        error_tracker.record(
                            e, ErrorSeverity.ERROR,
                            func.__module__, func.__name__,
                            {'attempts': attempt + 1}
                        )
                        raise
                    logger.warning(
                        f"{func.__name__} 第{attempt+1}次失败: {e}, "
                        f"{current_delay:.1f}s后重试"
                    )
                    if on_retry:
                        on_retry(attempt, e)
                    time.sleep(current_delay)
                    current_delay = min(current_delay * backoff, max_delay)
        return wrapper
    return decorator


def async_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable = None
):
    """异步重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        error_tracker.record(
                            e, ErrorSeverity.ERROR,
                            func.__module__, func.__name__,
                            {'attempts': attempt + 1}
                        )
                        raise
                    logger.warning(
                        f"{func.__name__} 第{attempt+1}次失败: {e}, "
                        f"{current_delay:.1f}s后重试"
                    )
                    if on_retry:
                        if asyncio.iscoroutinefunction(on_retry):
                            await on_retry(attempt, e)
                        else:
                            on_retry(attempt, e)
                    await asyncio.sleep(current_delay)
                    current_delay = min(current_delay * backoff, max_delay)
        return wrapper
    return decorator


# ==================== 熔断器 ====================

class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    熔断器模式

    连续失败达阈值后暂停请求，防止级联故障
    适用于IPFS网关、外部API等
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None

    @property
    def state(self) -> CircuitBreakerState:
        if self._state == CircuitBreakerState.OPEN:
            if (self._last_failure_time and
                    time.time() - self._last_failure_time > self.recovery_timeout):
                self._state = CircuitBreakerState.HALF_OPEN
                self._success_count = 0
                logger.info(f"熔断器 [{self.name}] -> 半开")
        return self._state

    def record_success(self):
        self._failure_count = 0
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitBreakerState.CLOSED
                logger.info(f"熔断器 [{self.name}] 恢复正常")

    def record_failure(self, error: Exception = None):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitBreakerState.OPEN:
                self._state = CircuitBreakerState.OPEN
                logger.warning(
                    f"熔断器 [{self.name}] 已熔断！"
                    f"连续失败 {self._failure_count} 次"
                )

    def can_proceed(self) -> bool:
        s = self.state
        return s in (CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN)

    def get_status(self) -> dict:
        return {
            'name': self.name,
            'state': self.state.value,
            'failures': self._failure_count,
            'successes': self._success_count
        }


def circuit_breaker(breaker: CircuitBreaker):
    """熔断器装饰器"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not breaker.can_proceed():
                raise GatewayError(
                    f"[{breaker.name}] 已熔断", gateway=breaker.name
                )
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure(e)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not breaker.can_proceed():
                raise GatewayError(
                    f"[{breaker.name}] 已熔断", gateway=breaker.name
                )
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure(e)
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# ==================== FastAPI异常处理 ====================

def setup_exception_handlers(app):
    """
    为FastAPI应用设置全局异常处理

    用法:
        from utils.error_handler import setup_exception_handlers
        app = FastAPI()
        setup_exception_handlers(app)
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    STATUS_MAP = {
        'CID_NOT_FOUND': 404,
        'IPFS_CONNECTION_ERROR': 503,
        'IPFS_TIMEOUT': 504,
        'GATEWAY_ERROR': 502,
        'RATE_LIMIT': 429,
        'CONFIG_ERROR': 500,
        'EVIDENCE_INTEGRITY_ERROR': 422,
        'MONITOR_ERROR': 500,
    }

    @app.exception_handler(ForensicsBaseError)
    async def forensics_handler(request: Request, exc: ForensicsBaseError):
        error_tracker.record(
            exc, ErrorSeverity.WARNING,
            'api', str(request.url.path),
            {'method': request.method, 'url': str(request.url)}
        )
        status = STATUS_MAP.get(exc.code, 500)
        return JSONResponse(status_code=status, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def general_handler(request: Request, exc: Exception):
        error_tracker.record(
            exc, ErrorSeverity.CRITICAL,
            'api', str(request.url.path),
            {'method': request.method, 'url': str(request.url)}
        )
        return JSONResponse(
            status_code=500,
            content={
                'error': True,
                'code': 'INTERNAL_ERROR',
                'message': '服务内部错误',
                'timestamp': datetime.utcnow().isoformat()
            }
        )

    @app.middleware("http")
    async def error_logging_middleware(request: Request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
            elapsed = time.time() - start
            if elapsed > 5.0:
                logger.warning(
                    f"慢请求: {request.method} {request.url.path} "
                    f"{elapsed:.2f}s"
                )
            return response
        except Exception as e:
            logger.error(
                f"请求异常: {request.method} {request.url.path}: {e}"
            )
            raise