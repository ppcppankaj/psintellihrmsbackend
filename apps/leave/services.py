"""Compatibility wrapper for legacy leave service imports."""

from importlib import util as importlib_util
from pathlib import Path
import sys
from types import ModuleType

_MODULE_NAME = f"{__name__}.leave_service"
_MODULE_PATH = Path(__file__).with_name("services").joinpath("leave_service.py")

if _MODULE_NAME in sys.modules:
    _leave_service = sys.modules[_MODULE_NAME]
else:
    _spec = importlib_util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Unable to load leave service module at {_MODULE_PATH}")

    _leave_service = importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_leave_service)
    # Register path so direct imports keep working.
    sys.modules[_MODULE_NAME] = _leave_service

LeaveCalculationService = _leave_service.LeaveCalculationService
LeaveBalanceService = _leave_service.LeaveBalanceService
LeaveApprovalService = _leave_service.LeaveApprovalService

__all__ = [
    "LeaveCalculationService",
    "LeaveBalanceService",
    "LeaveApprovalService",
]
