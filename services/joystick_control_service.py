#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""LOCAL + MANUAL joystick control with synchronous motor setpoints."""

import threading

from services.app_logger import AppLogger


class JoystickControlService(object):
    """Translates normalized joystick events into direct manual-drive calls."""

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
            manual_drive_port,
            max_speed_sp=600,
            auxiliary_speed_sp=400,
            axis_center=127,
            axis_max=255,
            left_auxiliary_motor_code="LMM",
            right_auxiliary_motor_code="RMM",
            poll_seconds=0.02,
            session_id="local-manual",
            logger=None):
        if manual_drive_port is None:
            raise ValueError("manual_drive_port is required.")
        self.joystick_port = joystick_port
        self.manual_drive_port = manual_drive_port
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
        self.session_id = session_id
        self.logger = logger or AppLogger

        self._translation = 0.0
        self._rotation = 0.0
        self._stop_event = threading.Event()
        self._thread = None
        self._acquired = False

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
        """Stops the worker and synchronously leaves all owned motors safe."""
        self._stop_event.set()
        try:
            self.joystick_port.close()
        except Exception as error:
            self.logger.error(
                "Unable to close joystick input: {}".format(error)
            )

        self.emergency_stop()
        if self._acquired:
            try:
                self.manual_drive_port.release(self.session_id, stop=False)
            except Exception as error:
                self.logger.error(
                    "Unable to release manual motor session: {}".format(error)
                )
            self._acquired = False

        if (self._thread is not None and
                self._thread is not threading.current_thread()):
            self._thread.join(timeout=2.0)

    def close(self):
        """Managed-service compatibility hook."""
        self.stop()

    def _run(self):
        try:
            opened_name = self.joystick_port.open()
            acquired = self.manual_drive_port.acquire(self.session_id)
            if not acquired.get("success"):
                raise RuntimeError(
                    acquired.get("error") or "Unable to acquire manual motors."
                )
            self._acquired = True
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
        """Processes one normalized joystick event."""
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
        """Synchronously stops every motor owned by the manual path."""
        self._translation = 0.0
        self._rotation = 0.0
        try:
            result = self.manual_drive_port.emergency_stop()
            self._log_failure("Emergency stop", result)
            return result
        except Exception as error:
            self.logger.error(
                "Unable to stop manual motors: {}".format(error)
            )
            return {"success": False, "error": str(error)}

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

        result = self.manual_drive_port.apply_drive_setpoint(
            self.session_id, left_speed, right_speed
        )
        self._log_failure("Differential drive", result)

    def _apply_auxiliary(self, motor_code, raw_value):
        if motor_code is None:
            return

        direction = int(raw_value)
        speed_sp = 0
        if direction != 0:
            speed_sp = self.auxiliary_speed_sp
            if direction > 0:
                speed_sp = -speed_sp

        result = self.manual_drive_port.apply_auxiliary_setpoint(
            self.session_id, motor_code, speed_sp
        )
        self._log_failure("Auxiliary motor {}".format(motor_code), result)

    def _log_failure(self, operation, result):
        if isinstance(result, dict) and not result.get("success", True):
            self.logger.error(
                "{} failed: {}".format(
                    operation,
                    result.get("error") or result.get("hardware_error")
                    or "unknown error"
                )
            )
