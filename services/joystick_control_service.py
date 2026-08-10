#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Local manual joystick control built on the existing Rover ports."""

import threading

from services.app_logger import AppLogger


class JoystickControlService(object):
    """Translates generic joystick events into Rover manual motor commands.

    This first implementation intentionally reuses the existing ``DrivePort``
    and ``MotorPort``. The dedicated low-latency motor path is introduced by a
    later evolution step; keeping that concern out of this service makes the
    initial local-manual behavior independently testable.
    """

    EVENT_KEY = 1
    EVENT_ABSOLUTE = 3

    BUTTON_EMERGENCY_STOP = 304
    AXIS_STEERING = 3
    AXIS_TRACTION = 1
    AXIS_AUXILIARY_HORIZONTAL = 16
    AXIS_AUXILIARY_VERTICAL = 17

    def __init__(
            self,
            joystick_port,
            drive_port,
            motor_port=None,
            max_speed_sp=600,
            auxiliary_speed_sp=400,
            axis_center=127,
            axis_max=255,
            left_auxiliary_motor_code="LMM",
            right_auxiliary_motor_code="RMM",
            poll_seconds=0.02,
            logger=None):
        self.joystick_port = joystick_port
        self.drive_port = drive_port
        self.motor_port = motor_port
        self.max_speed_sp = self._positive_int(max_speed_sp, "max_speed_sp")
        self.auxiliary_speed_sp = self._positive_int(
            auxiliary_speed_sp, "auxiliary_speed_sp"
        )
        self.axis_center = int(axis_center)
        self.axis_max = int(axis_max)
        if self.axis_center <= 0 or self.axis_max <= self.axis_center:
            raise ValueError(
                "axis_center must be positive and lower than axis_max."
            )
        self.left_auxiliary_motor_code = left_auxiliary_motor_code
        self.right_auxiliary_motor_code = right_auxiliary_motor_code
        self.poll_seconds = max(0.001, float(poll_seconds))
        self.logger = logger or AppLogger

        self._translation = 0.0
        self._rotation = 0.0
        self._stop_event = threading.Event()
        self._thread = None

    @staticmethod
    def _positive_int(value, name):
        parsed = int(value)
        if parsed <= 0:
            raise ValueError("{} must be positive.".format(name))
        return parsed

    def start(self):
        """Starts the controller-reading worker."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="JoystickControlThread"
        )
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """Stops the worker and leaves every manually controlled motor safe."""
        self._stop_event.set()
        try:
            self.joystick_port.close()
        except Exception as error:
            self.logger.error(
                "Unable to close joystick input: {}".format(error)
            )
        self.emergency_stop()
        if (self._thread is not None and
                self._thread is not threading.current_thread()):
            self._thread.join(timeout=2.0)

    def close(self):
        """Managed-service compatibility hook."""
        self.stop()

    def _run(self):
        try:
            opened_name = self.joystick_port.open()
            self.logger.status(
                "Local manual joystick connected: {}.".format(opened_name)
            )
            while not self._stop_event.is_set():
                event = self.joystick_port.read_event(self.poll_seconds)
                if event is not None:
                    self.process_event(event)
        except Exception as error:
            self.logger.error(
                "Local manual joystick control stopped: {}".format(error)
            )
            self.emergency_stop()

    def process_event(self, event):
        """Processes one normalized joystick event.

        Events are dictionaries containing ``type``, ``code`` and ``value``.
        This keeps application logic independent from Linux ``evdev``; the
        concrete Linux adapter is introduced separately.
        """
        if not isinstance(event, dict):
            return

        event_type = event.get("type")
        code = event.get("code")
        value = event.get("value")

        if (event_type == self.EVENT_KEY and
                code == self.BUTTON_EMERGENCY_STOP and value):
            self.emergency_stop()
            return

        if event_type != self.EVENT_ABSOLUTE:
            return

        if code == self.AXIS_TRACTION:
            self._translation = -self._normalize_axis(value)
            self._apply_differential_drive()
        elif code == self.AXIS_STEERING:
            self._rotation = self._normalize_axis(value)
            self._apply_differential_drive()
        elif code == self.AXIS_AUXILIARY_VERTICAL:
            self._apply_auxiliary(
                self.left_auxiliary_motor_code, value
            )
        elif code == self.AXIS_AUXILIARY_HORIZONTAL:
            self._apply_auxiliary(
                self.right_auxiliary_motor_code, value
            )

    def emergency_stop(self):
        """Immediately requests stop for traction and auxiliary motors."""
        self._translation = 0.0
        self._rotation = 0.0
        try:
            self.drive_port.stop()
        except Exception as error:
            self.logger.error(
                "Unable to stop traction motors: {}".format(error)
            )

        if self.motor_port is None:
            return

        for motor_code in (
                self.left_auxiliary_motor_code,
                self.right_auxiliary_motor_code):
            try:
                self.motor_port.stop_motor(motor_code)
            except Exception as error:
                self.logger.error(
                    "Unable to stop auxiliary motor {}: {}".format(
                        motor_code, error
                    )
                )

    def _normalize_axis(self, raw_value):
        value = float(raw_value)
        if value >= self.axis_center:
            span = float(self.axis_max - self.axis_center)
            normalized = (value - self.axis_center) / span
        else:
            span = float(self.axis_center)
            normalized = (value - self.axis_center) / span
        return max(-1.0, min(1.0, normalized))

    def _apply_differential_drive(self):
        left = self._translation + self._rotation
        right = self._translation - self._rotation
        denominator = max(abs(left), abs(right), 1.0)
        left_speed = int(round(
            (left / denominator) * self.max_speed_sp
        ))
        right_speed = int(round(
            (right / denominator) * self.max_speed_sp
        ))

        if left_speed == 0 and right_speed == 0:
            self.drive_port.stop()
            return

        self.drive_port.drive_tank(left_speed, right_speed)

    def _apply_auxiliary(self, motor_code, raw_value):
        if self.motor_port is None or motor_code is None:
            return

        direction = int(raw_value)
        if direction == 0:
            self.motor_port.stop_motor(motor_code)
            return

        speed_sp = self.auxiliary_speed_sp
        if direction > 0:
            speed_sp = -speed_sp
        self.motor_port.run_forever_motor(motor_code, speed_sp)
