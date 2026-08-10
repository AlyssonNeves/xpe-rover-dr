#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for deterministic local manual motor control."""

from abc import ABCMeta, abstractmethod


class ManualDrivePort(object, metaclass=ABCMeta):
    """Defines the synchronous local-manual motor-control contract."""

    @abstractmethod
    def acquire(self, session_id, motor_codes=None):
        """Acquires all motors required by one local manual session."""
        raise NotImplementedError

    @abstractmethod
    def apply_drive_setpoint(
        self, session_id, left_speed_sp, right_speed_sp, stop_action=None
    ):
        """Applies one differential-drive setpoint synchronously."""
        raise NotImplementedError

    @abstractmethod
    def apply_mecanum_setpoint(
        self, session_id, front_left_speed_sp, rear_left_speed_sp,
        front_right_speed_sp, rear_right_speed_sp, stop_action=None
    ):
        """Applies one four-wheel Mecanum setpoint synchronously."""
        raise NotImplementedError

    @abstractmethod
    def apply_auxiliary_setpoint(
        self, session_id, motor_code, speed_sp, stop_action=None
    ):
        """Applies one auxiliary-motor setpoint synchronously."""
        raise NotImplementedError

    @abstractmethod
    def emergency_stop(self, stop_action=None):
        """Synchronously stops every motor owned by the manual session."""
        raise NotImplementedError

    @abstractmethod
    def release(self, session_id, stop=True):
        """Releases the session and optionally stops all owned motors."""
        raise NotImplementedError
