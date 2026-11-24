"""Domain errors. Each carries a staff/LLM-safe message (no PHI)."""

from __future__ import annotations


class AppointmentError(Exception):
    """Base class for all scheduling errors."""


class NotFoundError(AppointmentError):
    pass


class InactiveDoctorError(AppointmentError):
    pass


class InvalidBookingTimeError(AppointmentError):
    pass


class OutsideAvailabilityError(AppointmentError):
    pass


class SchedulingConflictError(AppointmentError):
    def __init__(self, message: str, conflicting_ids: list[int]) -> None:
        super().__init__(message)
        self.conflicting_ids = conflicting_ids


class InvalidTransitionError(AppointmentError):
    pass


class StaleVersionError(AppointmentError):
    """The appointment was modified by someone else since it was read."""
