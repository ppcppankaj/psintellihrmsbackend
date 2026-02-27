"""Compatibility wrapper for the attendance service package."""

from importlib import util as importlib_util
from pathlib import Path
import sys

_MODULE_NAME = f"{__name__}.attendance_service"
_MODULE_PATH = Path(__file__).with_name('services').joinpath('attendance_service.py')

if _MODULE_NAME in sys.modules:
    _attendance_service = sys.modules[_MODULE_NAME]
else:
    _spec = importlib_util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Unable to load attendance service module at {_MODULE_PATH}")
    _attendance_service = importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_attendance_service)
    sys.modules[_MODULE_NAME] = _attendance_service

AttendanceService = _attendance_service.AttendanceService
GeoFenceService = _attendance_service.GeoFenceService
FraudDetectionService = _attendance_service.FraudDetectionService
ShiftManagementService = _attendance_service.ShiftManagementService

__all__ = [
    'AttendanceService',
    'GeoFenceService',
    'FraudDetectionService',
    'ShiftManagementService',
]
