#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for synchronous LOCAL + MANUAL motor control."""

from abc import ABCMeta, abstractmethod


class ManualDrivePort(object, metaclass=ABCMeta):
    """Defines the low-latency motor operations used by the joystick path."""

    @abstractmethod
    def acquire(self, session_id, motor_codes=None):
        """Acquires and preconnects the motors owned by one manual session."""
        raise NotImplementedError

    @abstractmethod
    def apply_drive_setpoint(
            self, session_id, left_speed_sp, right_speed_sp,
            stop_action=None):
        """Applies one differential-drive setpoint synchronously."""
        raise NotImplementedError

    @abstractmethod
    def apply_auxiliary_setpoint(
            self, session_id, motor_code, speed_sp, stop_action=None):
        """Applies one auxiliary-motor setpoint synchronously."""
        raise NotImplementedError

    @abstractmethod
    def emergency_stop(self, stop_action=None):
        """Synchronously stops every motor owned by the manual session."""
        raise NotImplementedError

    @abstractmethod
    def release(self, session_id, stop=True):
        """Releases the active manual session."""
        raise NotImplementedError
