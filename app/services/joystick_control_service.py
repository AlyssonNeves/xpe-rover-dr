#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""LOCAL + MANUAL joystick control with synchronous motor setpoints."""

import math
import threading

from app.operation_mode_service import Fronts


class NullApplicationLogger(object):
    """No-op logger used when no output logger is injected."""

    @staticmethod
    def status(message):
        del message

    @staticmethod
    def error(message):
        del message


class JoystickControlService(object):
    """Translates normalized joystick events into direct manual-drive calls."""

    EVENT_KEY = 1
    EVENT_ABSOLUTE = 3

    BUTTON_EMERGENCY_STOP = 304
    AXIS_DIRECTION_HORIZONTAL = 0
    AXIS_STEERING = 3
    AXIS_TRACTION = 1

    DRIVE_DIFFERENTIAL = "DIFFERENTIAL"
    DRIVE_MECANUM = "MECANUM"
    CENTRIC_CHASSIS = "CHASSIS"
    AXIS_AUXILIARY_HORIZONTAL = 16
    AXIS_AUXILIARY_VERTICAL = 17

    def __init__(
            self,
            joystick_port,
            manual_drive_port,
            max_speed_sp=600,
            auxiliary_speed_sp=400,
            axis_center=127,
            axis_deadzone=7,
            axis_max=255,
            axis_response_intensity=1.0,
            left_auxiliary_motor_code="LMM",
            right_auxiliary_motor_code="RMM",
            drive_mode=DRIVE_DIFFERENTIAL,
            front=Fronts.NOSE,
            centric=CENTRIC_CHASSIS,
            mecanum_strafe_compensation=1.0,
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
        axis_values = self._validate_axis_configuration(
            axis_center, axis_deadzone, axis_max
        )
        self.axis_center = axis_values[0]
        self.axis_deadzone = axis_values[1]
        self.axis_max = axis_values[2]
        self.axis_response_intensity = self._validate_response_intensity(
            axis_response_intensity
        )
        self.left_auxiliary_motor_code = left_auxiliary_motor_code
        self.right_auxiliary_motor_code = right_auxiliary_motor_code
        if drive_mode not in (self.DRIVE_DIFFERENTIAL, self.DRIVE_MECANUM):
            raise ValueError(
                "Unsupported manual drive mode: {}".format(drive_mode)
            )
        if centric != self.CENTRIC_CHASSIS:
            raise ValueError(
                "Unsupported Mecanum centric mode: {}".format(centric)
            )
        self.drive_mode = drive_mode
        if front not in Fronts.values():
            raise ValueError(
                "Unsupported Rover front: {}".format(front)
            )
        self.front = front
        self.centric = centric
        self.mecanum_strafe_compensation = float(mecanum_strafe_compensation)
        if self.mecanum_strafe_compensation <= 0.0:
            raise ValueError("mecanum_strafe_compensation must be positive.")
        self.poll_seconds = max(0.001, float(poll_seconds))
        self.session_id = session_id
        self.logger = logger or NullApplicationLogger

        self._strafe = 0.0
        self._translation = 0.0
        self._rotation = 0.0
        # A Bluetooth/input failure invalidates the current manual session.
        # A subsequent explicit restart is gated until both traction axes are
        # observed at their neutral position, preventing stale stick state from
        # restarting motion after the controller comes back.
        self._neutral_required = False
        self._neutral_pending_axes = set()
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
            if self._neutral_required:
                self.logger.status(
                    "Joystick safety gate active; return traction controls "
                    "to neutral before resuming motion."
                )
            while not self._stop_event.is_set():
                event = self.joystick_port.read_event(self.poll_seconds)
                if event is not None:
                    self.process_event(event)
        except Exception as error:
            if not self._stop_event.is_set():
                self.logger.error(
                    "Local manual joystick connection lost: {}".format(error)
                )
                self._invalidate_disconnected_session()
        finally:
            try:
                self.joystick_port.close()
            except Exception as error:
                self.logger.error(
                    "Unable to close joystick input after session: {}".format(
                        error
                    )
                )

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

        if self.drive_mode == self.DRIVE_MECANUM:
            self._process_mecanum_axis(code, value)
            return

        if code == self.AXIS_TRACTION:
            self._translation = -self._shaped_stick_axis(value)
            if self._neutral_gate_blocks(code, self._translation):
                return
            self._apply_differential_drive()
        elif code == self.AXIS_STEERING:
            self._rotation = self._shaped_stick_axis(value)
            if self._neutral_gate_blocks(code, self._rotation):
                return
            self._apply_differential_drive()
        elif code == self.AXIS_AUXILIARY_VERTICAL:
            if self._neutral_required:
                return
            self._apply_auxiliary(
                self.left_auxiliary_motor_code, value
            )
        elif code == self.AXIS_AUXILIARY_HORIZONTAL:
            if self._neutral_required:
                return
            self._apply_auxiliary(
                self.right_auxiliary_motor_code, value
            )

    def _process_mecanum_axis(self, code, value):
        """Updates CHASSIS-centric Mecanum state from the three drive axes."""
        if code == self.AXIS_DIRECTION_HORIZONTAL:
            self._strafe = self._shaped_stick_axis(value)
            if self._neutral_gate_blocks(code, self._strafe):
                return
        elif code == self.AXIS_TRACTION:
            # Linux evdev reports stick-up as negative Y.
            self._translation = -self._shaped_stick_axis(value)
            if self._neutral_gate_blocks(code, self._translation):
                return
        elif code == self.AXIS_STEERING:
            self._rotation = self._shaped_stick_axis(value)
            if self._neutral_gate_blocks(code, self._rotation):
                return
        else:
            # In Mecanum mode LMM/RMM are traction motors, so D-pad auxiliary
            # commands are intentionally unavailable.
            return

        self._apply_mecanum_drive()


    def _invalidate_disconnected_session(self):
        """Stops motion and invalidates input state after connection loss."""
        self._strafe = 0.0
        self._translation = 0.0
        self._rotation = 0.0
        self._neutral_required = True
        self._neutral_pending_axes = {
            self.AXIS_TRACTION, self.AXIS_STEERING
        }
        if self.drive_mode == self.DRIVE_MECANUM:
            self._neutral_pending_axes.add(self.AXIS_DIRECTION_HORIZONTAL)

        # Stop first: session invalidation must never delay the physical stop.
        self.emergency_stop()
        if self._acquired:
            try:
                result = self.manual_drive_port.release(
                    self.session_id, stop=True
                )
                self._log_failure("Manual session release", result)
            except Exception as error:
                self.logger.error(
                    "Unable to invalidate disconnected manual session: {}"
                    .format(error)
                )
            finally:
                self._acquired = False

    def _neutral_gate_blocks(self, axis_code, normalized_value):
        """Keeps post-disconnect motion blocked until controls are neutral."""
        if not self._neutral_required:
            return False

        if normalized_value == 0.0:
            self._neutral_pending_axes.discard(axis_code)

        controls_are_neutral = (
            self._translation == 0.0 and
            self._rotation == 0.0 and
            (self.drive_mode != self.DRIVE_MECANUM or self._strafe == 0.0)
        )
        if not self._neutral_pending_axes and controls_are_neutral:
            self._neutral_required = False
            self.logger.status(
                "Joystick controls neutral; manual motion is enabled again."
            )
        return True

    def emergency_stop(self):
        """Synchronously stops every motor owned by the manual path."""
        self._strafe = 0.0
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

    def _shaped_stick_axis(self, raw_value):
        """Applies deadzone removal and signed exponential response."""
        normalized = self._normalized_stick_axis(raw_value)
        if normalized == 0.0:
            return 0.0
        magnitude = self._exponential(
            abs(normalized), self.axis_response_intensity
        )
        return magnitude if normalized > 0.0 else -magnitude

    def _normalized_stick_axis(self, raw_value):
        """Normalizes the useful axis travel after removing the deadzone."""
        deviation = float(raw_value) - self.axis_center
        magnitude = abs(deviation)
        if magnitude <= self.axis_deadzone:
            return 0.0

        if deviation < 0.0:
            available_range = float(self.axis_center)
            sign = -1.0
        else:
            available_range = float(self.axis_max - self.axis_center)
            sign = 1.0

        usable_range = max(1.0, available_range - self.axis_deadzone)
        usable_magnitude = magnitude - self.axis_deadzone
        normalized_magnitude = max(
            0.0, min(1.0, usable_magnitude / usable_range)
        )
        return sign * normalized_magnitude

    # Compatibility alias retained during the incremental Sprint evolution.
    def _normalize_axis(self, raw_value):
        return self._normalized_stick_axis(raw_value)

    @staticmethod
    def _validate_axis_configuration(axis_center, axis_deadzone, axis_max):
        center = int(axis_center)
        deadzone = int(axis_deadzone)
        maximum = int(axis_max)
        if center <= 0 or center >= maximum:
            raise ValueError(
                "axis_center must be greater than zero and less than "
                "axis_max."
            )
        maximum_deadzone = min(center, maximum - center)
        if deadzone < 0 or deadzone >= maximum_deadzone:
            raise ValueError(
                "axis_deadzone must be non-negative and smaller than the "
                "usable range on both sides of axis_center."
            )
        return center, deadzone, maximum

    @staticmethod
    def _validate_response_intensity(axis_response_intensity):
        intensity = float(axis_response_intensity)
        if not math.isfinite(intensity) or intensity <= 0.0:
            raise ValueError(
                "axis_response_intensity must be finite and greater than "
                "zero."
            )
        return intensity

    @staticmethod
    def _exponential(value, intensity):
        value = max(0.0, min(1.0, float(value)))
        return (math.exp(intensity * value) - 1.0) / (
            math.exp(intensity) - 1.0
        )

    @staticmethod
    def _mecanum_ratios(x_value, y_value, rotation=0.0):
        """Returns normalized logical Mecanum wheel ratios.

        Positive ``y_value`` means forward, positive ``x_value`` means right
        strafe and positive ``rotation`` means clockwise rotation. Linux evdev
        reports stick-up as a negative raw Y value; the existing traction-axis
        inversion converts it to this positive-forward logical convention.

        Physical motor polarity is deliberately absent from these equations.
        It belongs to the EV3 hardware boundary, while Mecanum-only gear
        inversion/calibration belongs to ``ManualDriveService``.
        """
        x_value = float(x_value)
        y_value = float(y_value)
        rotation = float(rotation)
        denominator = max(
            abs(y_value) + abs(x_value) + abs(rotation),
            1.0
        )
        return (
            (y_value + x_value + rotation) / denominator,
            (y_value - x_value + rotation) / denominator,
            (y_value - x_value - rotation) / denominator,
            (y_value + x_value - rotation) / denominator
        )

    def _mecanum_setpoint(self, x_value, y_value, rotation=0.0):
        """Scales logical Mecanum ratios to the configured speed range."""
        return tuple(
            int(round(self.max_speed_sp * ratio))
            for ratio in self._mecanum_ratios(
                x_value, y_value, rotation
            )
        )


    def _apply_mecanum_drive(self):
        """Dispatches one CHASSIS-centric Mecanum setpoint synchronously."""
        x_value = self._strafe * self.mecanum_strafe_compensation
        wheel_ratios = self._mecanum_ratios(
            x_value, self._translation, self._rotation
        )
        wheel_ratios = self._apply_mecanum_direction(wheel_ratios)
        setpoint = tuple(
            int(round(self.max_speed_sp * ratio))
            for ratio in wheel_ratios
        )
        result = self.manual_drive_port.apply_mecanum_setpoint(
            self.session_id, *setpoint
        )
        self._log_failure("Mecanum CHASSIS drive", result)

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

        left_speed, right_speed = self._apply_differential_direction(
            left_speed, right_speed
        )
        result = self.manual_drive_port.apply_drive_setpoint(
            self.session_id, left_speed, right_speed
        )
        self._log_failure("Differential drive", result)


    def _apply_differential_direction(self, left_speed, right_speed):
        """Applies the operator-facing NOSE/TAIL convention."""
        if self.front == Fronts.TAIL:
            return -int(right_speed), -int(left_speed)
        return int(left_speed), int(right_speed)

    def _apply_mecanum_direction(self, wheel_ratios):
        """Rotates the operator translation frame for TAIL operation.

        Motor polarity and drivetrain calibration remain outside this
        transformation. Rotational direction is preserved while longitudinal
        and lateral commands are interpreted from the selected Rover front.
        """
        front_left, rear_left, front_right, rear_right = wheel_ratios
        if self.front == Fronts.NOSE:
            return wheel_ratios
        return (
            -rear_right,
            -front_right,
            -rear_left,
            -front_left
        )

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
