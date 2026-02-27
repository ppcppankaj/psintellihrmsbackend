from contextvars import ContextVar
from typing import Optional

# Async-safe storage for correlation ID
_correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

def set_correlation_id(correlation_id: str) -> None:
    _correlation_id_var.set(correlation_id)

def get_correlation_id() -> Optional[str]:
    return _correlation_id_var.get()

class CorrelationIdFilter:
    def filter(self, record):
        record.correlation_id = get_correlation_id() or 'unknown'
        return True

