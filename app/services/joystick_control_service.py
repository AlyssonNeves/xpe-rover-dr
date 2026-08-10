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


class NullJoystickConnectionStatus(object):
    """No-op operator feedback when no connection display is assembled."""

    @staticmethod
    def show_joystick_connection_error(message, retry_seconds):
        del message
        del retry_seconds

    @staticmethod
    def show_joystick_connected(device_name):
        del device_name


class JoystickControlService(object):
    """Translates normalized joystick events into direct manual-drive calls."""

    EVENT_KEY = 1
    EVENT_ABSOLUTE = 3
    MAX_EVENTS_PER_CYCLE = 64

    BUTTON_EMERGENCY_STOP = 304
    BUTTON_FIELD_RECENTER = 307
    AXIS_DIRECTION_HORIZONTAL = 0
    AXIS_STEERING = 3
    AXIS_TRACTION = 1

    DRIVE_DIFFERENTIAL = "DIFFERENTIAL"
    DRIVE_MECANUM = "MECANUM"
    CENTRIC_CHASSIS = "CHASSIS"
    CENTRIC_FIELD = "FIELD"
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
            logger=None,
            device_name="Wireless Controller",
            connection_retry_seconds=3.0,
            connection_status_port=None,
            heading_query_port=None,
            field_heading_reference_port=None,
            emergency_stop_button_code=BUTTON_EMERGENCY_STOP,
            field_recenter_button_code=BUTTON_FIELD_RECENTER,
            field_recenter_enabled=False,
            field_recenter_requires_neutral=True):
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
        if centric not in (self.CENTRIC_CHASSIS, self.CENTRIC_FIELD):
            raise ValueError(
                "Unsupported Mecanum centric mode: {}".format(centric)
            )
        if (drive_mode == self.DRIVE_MECANUM and
                centric == self.CENTRIC_FIELD and
                heading_query_port is None):
            raise ValueError(
                "FIELD-centric Mecanum control requires HeadingQueryPort."
            )
        self.drive_mode = drive_mode
        if front not in Fronts.values():
            raise ValueError(
                "Unsupported Rover front: {}".format(front)
            )
        self.front = front
        self.centric = centric
        self.heading_query_port = heading_query_port
        self.field_heading_reference_port = field_heading_reference_port
        self.emergency_stop_button_code = int(emergency_stop_button_code)
        self.field_recenter_button_code = int(field_recenter_button_code)
        if self.emergency_stop_button_code == self.field_recenter_button_code:
            raise ValueError("Joystick safety button codes must be distinct.")
        self.field_recenter_enabled = bool(field_recenter_enabled)
        self.field_recenter_requires_neutral = bool(
            field_recenter_requires_neutral
        )
        if (drive_mode == self.DRIVE_MECANUM and
                centric == self.CENTRIC_FIELD and
                self.field_recenter_enabled and
                self.field_heading_reference_port is None):
            raise ValueError(
                "FIELD recenter requires FieldHeadingReferenceCommandPort."
            )
        self.mecanum_strafe_compensation = float(mecanum_strafe_compensation)
        if self.mecanum_strafe_compensation <= 0.0:
            raise ValueError("mecanum_strafe_compensation must be positive.")
        self.poll_seconds = max(0.001, float(poll_seconds))
        self.session_id = session_id
        self.logger = logger or NullApplicationLogger
        self.device_name = str(device_name or "Wireless Controller")
        self.connection_retry_seconds = max(
            0.05, float(connection_retry_seconds)
        )
        self.connection_status_port = (
            connection_status_port or NullJoystickConnectionStatus()
        )

        self._strafe = 0.0
        self._translation = 0.0
        self._rotation = 0.0
        # A Bluetooth/input failure invalidates the current manual session.
        # A subsequent explicit restart is gated until both traction axes are
        # observed at their neutral position, preventing stale stick state from
        # restarting motion after the controller comes back.
        self._neutral_required = False
        self._field_heading_unavailable = False
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
        """Keeps LOCAL + MANUAL control available across disconnects."""
        while not self._stop_event.is_set():
            try:
                self._stop_before_connection_attempt()
                if self._joystick_is_available() is False:
                    self._notify_connection_error(
                        "Joystick not found. Trying Bluetooth connection."
                    )
                opened_name = self.joystick_port.open()
                acquired = self.manual_drive_port.acquire(self.session_id)
                if not acquired.get("success"):
                    raise RuntimeError(
                        acquired.get("error") or
                        "Unable to acquire manual motors."
                    )
                self._acquired = True
                self._reset_axis_state_for_connection()
                self._refresh_connection_axis_state()
                self.logger.status(
                    "Local manual joystick connected: {}.".format(opened_name)
                )
                if self._neutral_required:
                    self.logger.status(
                        "Joystick safety gate active; return traction "
                        "controls to neutral before resuming motion."
                    )
                self._notify_connected(opened_name)

                while not self._stop_event.is_set():
                    events = self.joystick_port.read_event_batch(
                        self.poll_seconds, self.MAX_EVENTS_PER_CYCLE
                    )
                    if events:
                        self.process_event_batch(events)
            except Exception as error:
                if not self._stop_event.is_set():
                    self.logger.error(
                        "Local manual joystick unavailable: {}".format(error)
                    )
                    self._invalidate_disconnected_session()
                    self._notify_connection_error(
                        "Joystick unavailable. Automatic retry pending."
                    )
            finally:
                try:
                    self.joystick_port.close()
                except Exception as error:
                    self.logger.error(
                        "Unable to close joystick input after session: {}"
                        .format(error)
                    )

            if self._stop_event.wait(self.connection_retry_seconds):
                break

    def _joystick_is_available(self):
        probe = getattr(self.joystick_port, "is_available", None)
        if not callable(probe):
            return None
        try:
            return bool(probe())
        except Exception as error:
            self.logger.error(
                "Unable to probe joystick availability: {}".format(error)
            )
            return None

    def _stop_before_connection_attempt(self):
        """Leaves physical outputs safe before every connection attempt."""
        self._strafe = 0.0
        self._translation = 0.0
        self._rotation = 0.0
        self.emergency_stop()

    def _reset_axis_state_for_connection(self):
        """Never reuses axis values from a previous Bluetooth session."""
        self._strafe = 0.0
        self._translation = 0.0
        self._rotation = 0.0

    def _refresh_connection_axis_state(self):
        """Seeds the neutral safety gate from the physical stick position.

        The evdev adapter discards queued movement history and returns a fresh
        absolute snapshot. No motor command is emitted while this snapshot is
        applied; movement remains blocked until every active traction axis is
        neutral. Ports from earlier tests that do not expose the optional
        snapshot operation keep the pre-S02.24 event-driven behavior.
        """
        refresh = getattr(self.joystick_port, "refresh_absolute_state", None)
        if not callable(refresh):
            return None

        axis_codes = {self.AXIS_TRACTION, self.AXIS_STEERING}
        if self.drive_mode == self.DRIVE_MECANUM:
            axis_codes.add(self.AXIS_DIRECTION_HORIZONTAL)
        requested_codes = tuple(sorted(axis_codes))
        snapshot = refresh(requested_codes)
        if not isinstance(snapshot, dict):
            raise RuntimeError("Joystick axis snapshot must be a dictionary.")
        missing = [
            code for code in requested_codes if code not in snapshot
        ]
        if missing:
            raise RuntimeError(
                "Joystick axis snapshot is missing code(s): {0}.".format(
                    ", ".join(str(code) for code in missing)
                )
            )

        self._neutral_required = True
        self._neutral_pending_axes = set(requested_codes)
        for code in requested_codes:
            self._apply_axis_snapshot_value(code, snapshot[code])
        return snapshot

    def _apply_axis_snapshot_value(self, code, raw_value):
        """Updates internal axis state without dispatching motor commands."""
        if code == self.AXIS_DIRECTION_HORIZONTAL:
            self._strafe = self._shaped_stick_axis(raw_value)
            normalized = self._strafe
        elif code == self.AXIS_TRACTION:
            self._translation = -self._shaped_stick_axis(raw_value)
            normalized = self._translation
        elif code == self.AXIS_STEERING:
            self._rotation = self._shaped_stick_axis(raw_value)
            normalized = self._rotation
        else:
            return

        if normalized == 0.0:
            self._neutral_pending_axes.discard(code)

        controls_are_neutral = (
            self._translation == 0.0 and
            self._rotation == 0.0 and
            (self.drive_mode != self.DRIVE_MECANUM or self._strafe == 0.0)
        )
        if not self._neutral_pending_axes and controls_are_neutral:
            self._neutral_required = False
            self.logger.status(
                "Joystick startup snapshot neutral; manual motion enabled."
            )

    def _notify_connection_error(self, message):
        try:
            self.connection_status_port.show_joystick_connection_error(
                message, self.connection_retry_seconds
            )
        except Exception as error:
            self.logger.error(
                "Unable to update Bluetooth error status: {}".format(error)
            )

    def _notify_connected(self, device_name):
        try:
            self.connection_status_port.show_joystick_connected(device_name)
        except Exception as error:
            self.logger.error(
                "Unable to restore joystick connected status: {}".format(error)
            )

    def process_event_batch(self, events):
        """Processes one bounded joystick cycle through one public path.

        Absolute-axis events are consolidated to their newest value before
        motion is calculated. Key presses preserve safety priority, and at
        most one traction setpoint is emitted for the complete batch.
        """
        latest_absolute = {}
        pressed_keys = set()
        for event in events or ():
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            code = event.get("code")
            if event_type == self.EVENT_ABSOLUTE:
                latest_absolute[code] = event.get("value")
            elif event_type == self.EVENT_KEY and event.get("value") == 1:
                pressed_keys.add(code)

        if self.emergency_stop_button_code in pressed_keys:
            self.emergency_stop()
            self._require_traction_neutral()
            return

        traction_changed = self._update_traction_axes(latest_absolute)

        if self.field_recenter_button_code in pressed_keys:
            self._handle_field_recenter()

        if traction_changed and not self._neutral_required:
            if self.drive_mode == self.DRIVE_MECANUM:
                self._apply_mecanum_drive()
            else:
                self._apply_differential_drive()

        if (self.drive_mode == self.DRIVE_DIFFERENTIAL and
                not self._neutral_required):
            self._apply_auxiliary_batch(latest_absolute)

    def _update_traction_axes(self, latest_absolute):
        """Updates current traction state without dispatching motor commands."""
        changed = False
        axis_order = [self.AXIS_TRACTION, self.AXIS_STEERING]
        if self.drive_mode == self.DRIVE_MECANUM:
            axis_order.insert(0, self.AXIS_DIRECTION_HORIZONTAL)

        for code in axis_order:
            if code not in latest_absolute:
                continue
            value = latest_absolute[code]
            if code == self.AXIS_DIRECTION_HORIZONTAL:
                self._strafe = self._shaped_stick_axis(value)
                normalized = self._strafe
            elif code == self.AXIS_TRACTION:
                # Linux evdev reports stick-up as negative Y.
                self._translation = -self._shaped_stick_axis(value)
                normalized = self._translation
            else:
                self._rotation = self._shaped_stick_axis(value)
                normalized = self._rotation

            changed = True
            if self._neutral_required:
                self._neutral_gate_blocks(code, normalized)
        return changed

    def _apply_auxiliary_batch(self, latest_absolute):
        """Applies only the newest D-pad values from the current cycle."""
        if self.AXIS_AUXILIARY_VERTICAL in latest_absolute:
            self._apply_auxiliary(
                self.left_auxiliary_motor_code,
                latest_absolute[self.AXIS_AUXILIARY_VERTICAL]
            )
        if self.AXIS_AUXILIARY_HORIZONTAL in latest_absolute:
            self._apply_auxiliary(
                self.right_auxiliary_motor_code,
                latest_absolute[self.AXIS_AUXILIARY_HORIZONTAL]
            )

    def _require_traction_neutral(self):
        """Arms neutral safety for every active traction axis."""
        self._neutral_required = True
        self._neutral_pending_axes = {
            self.AXIS_TRACTION, self.AXIS_STEERING
        }
        if self.drive_mode == self.DRIVE_MECANUM:
            self._neutral_pending_axes.add(self.AXIS_DIRECTION_HORIZONTAL)

    def _handle_field_recenter(self):
        """Redefines the FIELD zero from fresh cached heading when safe."""
        if not self._field_recenter_is_applicable():
            return False

        if (self.field_recenter_requires_neutral and
                not self._field_recenter_controls_neutral()):
            self.logger.error(
                "FIELD zero not redefined: traction controls must be neutral."
            )
            return False

        result = (
            self.field_heading_reference_port.set_current_heading_as_zero()
        )
        if not result.get("success"):
            self.logger.error(
                "FIELD zero not redefined: fresh gyro heading unavailable."
            )
            return False

        self.logger.status(
            "FIELD zero redefined from canonical heading {0:.2f} deg.".format(
                float(result["reference_heading_deg"])
            )
        )
        return True

    def _field_recenter_is_applicable(self):
        return (
            self.field_recenter_enabled and
            self.drive_mode == self.DRIVE_MECANUM and
            self.centric == self.CENTRIC_FIELD and
            self.field_heading_reference_port is not None
        )

    def _field_recenter_controls_neutral(self):
        return (
            self._strafe == 0.0 and
            self._translation == 0.0 and
            self._rotation == 0.0
        )

    def _invalidate_disconnected_session(self):
        """Stops motion and invalidates input state after connection loss."""
        self._strafe = 0.0
        self._translation = 0.0
        self._rotation = 0.0
        self._require_traction_neutral()

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
            if (self.drive_mode == self.DRIVE_MECANUM and
                    self.centric == self.CENTRIC_FIELD and
                    self._field_heading_unavailable):
                if self.heading_query_port.get_heading_deg() is None:
                    return True
                self._field_heading_unavailable = False
                self.logger.status(
                    "Fresh heading restored; neutral controls confirmed "
                    "before FIELD motion resumes."
                )
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
        """Dispatches one CHASSIS- or FIELD-centric Mecanum setpoint."""
        translation_vector = self._mecanum_translation_vector()
        if translation_vector is None:
            return
        x_value, y_value = translation_vector
        wheel_ratios = self._mecanum_ratios(
            x_value, y_value, self._rotation
        )
        wheel_ratios = self._apply_mecanum_direction(wheel_ratios)
        setpoint = tuple(
            int(round(self.max_speed_sp * ratio))
            for ratio in wheel_ratios
        )
        result = self.manual_drive_port.apply_mecanum_setpoint(
            self.session_id, *setpoint
        )
        self._log_failure("Mecanum {} drive".format(self.centric), result)

    def _mecanum_translation_vector(self):
        """Returns the translation vector in the selected reference frame.

        FIELD mode reads only ``HeadingQueryPort``. The query is expected to
        expose a fresh cached sample and must never perform physical gyro I/O
        on this latency-sensitive joystick path.
        """
        if self.centric == self.CENTRIC_CHASSIS:
            return (
                self._strafe * self.mecanum_strafe_compensation,
                self._translation
            )

        heading_deg = self.heading_query_port.get_heading_deg()
        if heading_deg is None:
            self._handle_field_heading_unavailable()
            return None

        heading_rad = math.radians(float(heading_deg))
        cosine = math.cos(heading_rad)
        sine = math.sin(heading_rad)
        rotated_x = self._strafe * cosine - self._translation * sine
        rotated_y = self._strafe * sine + self._translation * cosine
        return (
            rotated_x * self.mecanum_strafe_compensation,
            rotated_y
        )

    def _handle_field_heading_unavailable(self):
        """Stops FIELD motion and arms neutral safety when heading is stale."""
        first_failure = not self._field_heading_unavailable
        self._field_heading_unavailable = True
        if first_failure:
            self.emergency_stop()
            self.logger.error(
                "Fresh heading unavailable; FIELD traction stopped."
            )
        self._require_field_neutral()

    def _require_field_neutral(self):
        self._require_traction_neutral()

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
