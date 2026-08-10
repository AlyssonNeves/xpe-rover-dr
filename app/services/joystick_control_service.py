#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Deterministic local manual joystick control for Rover motors."""

import math
import threading
import time
import uuid

from app.operation_mode_service import (
    Centrics,
    DifferentialModes,
    Drives,
    Fronts,
    coerce_operation_mode
)
from ports.runtime_component_port import RuntimeComponentPort


class NullApplicationLogger(object):
    """No-op logger used when no logging port is injected."""

    @staticmethod
    def status(message):
        del message

    @staticmethod
    def warning(message):
        del message

    @staticmethod
    def error(message):
        del message


class NullJoystickConnectionStatus(object):
    """No-op output used when no operator display is assembled."""

    @staticmethod
    def show_joystick_connection_error(message, retry_seconds):
        del message
        del retry_seconds

    @staticmethod
    def show_joystick_connected(device_name):
        del device_name


class NullStartupProgress(object):
    """No-op output used when no startup display is assembled."""

    @staticmethod
    def show_startup_progress(message):
        del message


class NullStatusLed(object):
    """No-op output used when no operational LED adapter is assembled."""

    @staticmethod
    def set_fault(source, active=True):
        del source
        del active


class JoystickControlService(RuntimeComponentPort):
    """Translates the newest joystick state into direct EV3 motor commands.

    ``DIFFERENTIAL`` uses left-stick Y for forward/backward translation and
    right-stick X for normalized arcade-drive rotation. ``MECANUM`` uses the
    left-stick X/Y vector for translation and right-stick X for rotation; stick
    displacement directly controls speed, without a trigger accelerator. In
    ``CHASSIS``-centric mode, the standard normalized Mecanum equations combine
    translation and rotation. In ``FIELD``-centric mode, only a fresh cached
    gyro heading is read; physical sensor I/O remains on a dedicated monitor
    thread. A forward stick command produces
    positive logical setpoints for all four wheels; configured Mecanum factors
    and global motor polarity are applied only by the downstream layers. This
    service emits logical wheel setpoints only: global motor polarity is
    applied by the EV3 hardware layer, and Mecanum gear-train factors are
    applied by ``ManualDriveService``.
    """

    EVENT_KEY = 1
    EVENT_ABSOLUTE = 3

    BUTTON_STOP = 304
    BUTTON_FIELD_RECENTER = 307
    AXIS_DIRECTION_HORIZONTAL = 0
    AXIS_DIRECTION_VERTICAL = 1
    AXIS_ROTATION_HORIZONTAL = 3
    AXIS_AUXILIARY_HORIZONTAL = 16
    AXIS_AUXILIARY_VERTICAL = 17
    MAX_EVENTS_PER_CYCLE = 64

    def __init__(self, joystick_port, manual_drive_port, device_name,
                 max_speed_sp, auxiliary_speed_sp, axis_center, axis_deadzone,
                 axis_max, axis_response_intensity, left_auxiliary_motor_code,
                 right_auxiliary_motor_code, poll_seconds,
                 connection_retry_seconds, mecanum_strafe_compensation,
                 operation_mode, heading_query_port=None,
                 field_heading_reference_port=None, stop_button_code=None,
                 field_recenter_button_code=None,
                 field_recenter_enabled=False,
                 field_recenter_requires_neutral=True, logger=None,
                 connection_status_port=None, startup_progress_port=None,
                 status_led_port=None, neutral_stability_seconds=0.25,
                 neutral_poll_seconds=0.05, monotonic_clock=None):
        self.joystick_port = joystick_port
        self.manual_drive_port = manual_drive_port
        self.device_name = device_name
        self.logger = logger or NullApplicationLogger
        self.connection_status_port = (
            connection_status_port or NullJoystickConnectionStatus()
        )
        self.startup_progress_port = (
            startup_progress_port or NullStartupProgress()
        )
        self.status_led_port = status_led_port or NullStatusLed()
        self._monotonic_clock = monotonic_clock or time.monotonic
        self.max_speed_sp = int(max_speed_sp)
        self.auxiliary_speed_sp = int(auxiliary_speed_sp)
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
        self.poll_seconds = float(poll_seconds)
        self.connection_retry_seconds = max(
            0.05, float(connection_retry_seconds)
        )
        neutral_timing = self._validate_neutral_timing(
            neutral_stability_seconds, neutral_poll_seconds
        )
        self.neutral_stability_seconds = neutral_timing[0]
        self.neutral_poll_seconds = neutral_timing[1]
        resolved_mode = self._validate_operation_mode(operation_mode)
        self.drive = resolved_mode.drive
        self.front = resolved_mode.front
        self.centric = resolved_mode.centric
        self.differential_mode = resolved_mode.differential_mode
        self.heading_query_port = heading_query_port
        self.field_heading_reference_port = field_heading_reference_port
        self.stop_button_code = int(
            self.BUTTON_STOP if stop_button_code is None else stop_button_code
        )
        self.field_recenter_button_code = int(
            self.BUTTON_FIELD_RECENTER
            if field_recenter_button_code is None
            else field_recenter_button_code
        )
        self.field_recenter_enabled = bool(field_recenter_enabled)
        self.field_recenter_requires_neutral = bool(
            field_recenter_requires_neutral
        )
        self._validate_field_control_dependencies()
        self.mecanum_strafe_compensation = max(
            0.0, float(mecanum_strafe_compensation)
        )
        self._direction_x = 0.0
        self._direction_y = 0.0
        self._rotation_x = 0.0
        self._last_drive = None
        self._last_mecanum = None
        self._stop_event = threading.Event()
        self._thread = None
        self._state_lock = threading.RLock()
        self._session_id = None
        self._prepared_device_name = None
        self._neutral_required = False
        self._neutral_pending_axes = set()
        self._startup_axis_raw_values = {}
        self._field_heading_unavailable = False
        self._auxiliary_state = {
            self.left_auxiliary_motor_code: 0,
            self.right_auxiliary_motor_code: 0
        }

    def prepare_start(self):
        """Opens Bluetooth and acquires motors before later startup checks.

        Initialization Status is already visible when this method runs. The
        Bluetooth joystick is the first physical dependency checked. Motor I/O
        begins only after the joystick has actually opened; FIELD gyro checks
        remain later in the application startup sequence.
        """
        while not self._stop_event.is_set():
            connected = False
            try:
                if self._joystick_is_available() is False:
                    self._notify_joystick_connection_error(
                        "Joystick not found. Trying to connect."
                    )
                opened_name = self._open_joystick_for_startup()
                connected = True
                self._prepare_new_connection()
                with self._state_lock:
                    self._prepared_device_name = opened_name
                return
            except Exception as error:
                if self._stop_event.is_set():
                    break
                self._log_connection_failure(error, connected, False)
                self._cleanup_startup_attempt(connected)
                if self._stop_event.wait(self.connection_retry_seconds):
                    break
        return

    def _cleanup_startup_attempt(self, connected):
        """Avoids motor I/O when Bluetooth itself has not opened yet."""
        if connected:
            self._cleanup_connection()
            return
        try:
            self.joystick_port.close()
        except Exception as error:
            self.logger.error(
                "Unable to close joystick input: {0}".format(error)
            )
        with self._state_lock:
            self._reset_input_state_locked()
            self._require_neutral_locked(require_all_axes=True)

    def _open_joystick_for_startup(self):
        """Opens the joystick and restores Initialization Status on success."""
        open_started = self._monotonic_clock()
        opened_name = self.joystick_port.open()
        open_elapsed = self._monotonic_clock() - open_started
        self._publish_startup_progress(
            "Joystick connected. Starting control initialization."
        )
        self._publish_startup_progress(
            "Joystick opened in {0:.3f} s.".format(open_elapsed)
        )
        return opened_name

    def start(self):
        """Starts the Bluetooth joystick input loop."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="JoystickControlThread"
        )
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """Stops input and synchronously stops every manual motor."""
        self._stop_event.set()
        try:
            self.joystick_port.close()
        except Exception as error:
            self.logger.error(
                "Unable to close joystick input during shutdown: {0}".format(error)
            )
        self._stop_all()
        self._release_manual_session(stop=True)
        with self._state_lock:
            self._prepared_device_name = None
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)

    def close(self):
        """Provides the managed-resource close contract."""
        self.stop()

    def _run(self):
        """Keeps LOCAL + MANUAL control available across disconnects."""
        while not self._stop_event.is_set():
            connected = False
            control_ready = False
            try:
                opened_name = self._take_prepared_device_name()
                if opened_name is None:
                    if self._joystick_is_available() is False:
                        self._notify_joystick_connection_error(
                            "Joystick not found. Trying to connect."
                        )
                    opened_name = self._open_joystick_for_startup()
                    self._prepare_new_connection()
                connected = True
                self._verify_runtime_dependencies()
                self._refresh_startup_axis_state()
                self._wait_for_startup_neutral()
                control_ready = True
                self.logger.status(
                    "All traction axes neutral. Rover control ready."
                )
                self.logger.status(
                    "Joystick connected: {0}.".format(opened_name)
                )
                self._notify_joystick_connected(opened_name)
                self._run_connected_session()
            except Exception as error:
                if not self._stop_event.is_set():
                    self._log_connection_failure(
                        error, connected, control_ready
                    )
            finally:
                self._cleanup_connection()

            if self._stop_event.wait(self.connection_retry_seconds):
                break

    def _take_prepared_device_name(self):
        """Consumes the connection prepared synchronously during startup."""
        with self._state_lock:
            device_name = self._prepared_device_name
            self._prepared_device_name = None
        return device_name

    def _verify_runtime_dependencies(self):
        """Checks dependencies intentionally sequenced after Bluetooth/motors."""
        if self.centric != Centrics.FIELD:
            return
        if self.heading_query_port.get_heading_deg() is None:
            raise RuntimeError(
                "Gyro heading is unavailable for FIELD-centric control."
            )
        self._publish_startup_progress(
            "Gyro heading ready. Checking joystick neutral."
        )

    def _prepare_new_connection(self):
        with self._state_lock:
            # Never retain axis values from a previous Bluetooth session.
            self._reset_input_state_locked()
            # Every active traction axis must be observed at neutral before
            # movement is accepted after startup or reconnection.
            self._require_neutral_locked(require_all_axes=True)
        self._acquire_manual_session()

    def _refresh_startup_axis_state(self):
        """Returns and applies a complete current traction-axis snapshot."""
        refresh = getattr(
            self.joystick_port, "refresh_absolute_state", None
        )
        if not callable(refresh):
            raise RuntimeError(
                "Joystick input port cannot read current axis positions."
            )
        self._publish_startup_progress(
            "Reading current joystick position."
        )
        snapshot = refresh(tuple(sorted(self._traction_axis_codes())))
        self._apply_startup_axis_snapshot(snapshot)
        return snapshot

    def _wait_for_startup_neutral(self):
        """Verifies stable physical neutral while discarding all input."""
        stable_since = None
        last_message = None
        verifying_message = (
            "Neutral detected. Verifying {0:.2f} s stability.".format(
                self.neutral_stability_seconds
            )
        )

        while not self._stop_event.is_set():
            now = self._monotonic_clock()
            with self._state_lock:
                wait_message = self._neutral_wait_message_locked()

            if wait_message is None:
                if stable_since is None:
                    stable_since = now
                    if verifying_message != last_message:
                        self._publish_startup_progress(verifying_message)
                        last_message = verifying_message
                elif now - stable_since >= self.neutral_stability_seconds:
                    with self._state_lock:
                        self._neutral_required = False
                        self._neutral_pending_axes.clear()
                    self._publish_startup_progress(
                        "Joystick neutral stable for {0:.3f} s.".format(
                            self.neutral_stability_seconds
                        )
                    )
                    return
            else:
                stable_since = None
                if wait_message != last_message:
                    self._publish_startup_progress(wait_message)
                    with self._state_lock:
                        diagnostic = self._neutral_diagnostic_message_locked()
                    self.logger.status(diagnostic)
                    last_message = wait_message

            if self._stop_event.wait(self.neutral_poll_seconds):
                break
            snapshot = self.joystick_port.refresh_absolute_state(
                tuple(sorted(self._traction_axis_codes()))
            )
            self._apply_startup_axis_snapshot(snapshot)

        raise RuntimeError("Joystick startup was cancelled.")

    def _apply_startup_axis_snapshot(self, snapshot):
        """Applies only raw traction-axis state; no motor command is sent."""
        if not isinstance(snapshot, dict):
            raise RuntimeError(
                "Joystick current-axis snapshot is unavailable."
            )
        required_axes = self._traction_axis_codes()
        missing_axes = required_axes - set(snapshot)
        if missing_axes:
            labels = [
                self._traction_axis_label(code)
                for code in sorted(missing_axes)
            ]
            raise RuntimeError(
                "Joystick snapshot missing required axis: {0}.".format(
                    ", ".join(labels)
                )
            )

        with self._state_lock:
            self._startup_axis_raw_values = {}
            for code in required_axes:
                raw_value = int(snapshot[code])
                self._startup_axis_raw_values[code] = raw_value
                shaped = self._shaped_stick_axis(raw_value)
                if code == self.AXIS_DIRECTION_HORIZONTAL:
                    self._direction_x = shaped
                elif code == self.AXIS_DIRECTION_VERTICAL:
                    self._direction_y = -shaped
                elif code == self.AXIS_ROTATION_HORIZONTAL:
                    self._rotation_x = shaped
            self._neutral_pending_axes = {
                code for code in required_axes
                if self._axis_value(code) != 0.0
            }

    def _neutral_wait_message_locked(self):
        """Returns an actionable message for axes outside the deadzone."""
        blocked_axes = {
            code for code in self._traction_axis_codes()
            if self._axis_value(code) != 0.0
        }
        blocked_axes.update(self._neutral_pending_axes)
        if not blocked_axes:
            return None
        values = []
        for code in sorted(blocked_axes):
            label = self._traction_axis_label(code)
            raw_value = self._startup_axis_raw_values.get(code)
            if raw_value is None:
                values.append(label)
            else:
                values.append("{0}={1}".format(label, raw_value))
        return "Center joystick: {0}.".format(", ".join(values))

    def _neutral_diagnostic_message_locked(self):
        """Builds raw-axis details for logs without crowding the EV3 LCD."""
        minimum = self.axis_center - self.axis_deadzone
        maximum = self.axis_center + self.axis_deadzone
        values = []
        for code in sorted(self._traction_axis_codes()):
            label = self._traction_axis_label(code)
            raw_value = self._startup_axis_raw_values.get(code)
            values.append("{0}={1}".format(label, raw_value))
        return (
            "Joystick neutral check: {0}; accepted raw range={1}..{2}."
        ).format(", ".join(values), minimum, maximum)

    @classmethod
    def _traction_axis_label(cls, code):
        labels = {
            cls.AXIS_DIRECTION_HORIZONTAL: "LX",
            cls.AXIS_DIRECTION_VERTICAL: "LY",
            cls.AXIS_ROTATION_HORIZONTAL: "RX"
        }
        return labels.get(code, str(code))

    def _run_connected_session(self):
        while not self._stop_event.is_set():
            events = self.joystick_port.read_event_batch(
                self.poll_seconds,
                self.MAX_EVENTS_PER_CYCLE
            )
            if events:
                self.process_event_batch(events)

    def _joystick_is_available(self):
        """Checks evdev availability when supported by the input adapter."""
        availability_check = getattr(
            self.joystick_port, "is_available", None
        )
        if not callable(availability_check):
            return None
        try:
            return bool(availability_check())
        except Exception as error:
            self.logger.error(
                "Unable to inspect joystick availability: {0}".format(error)
            )
            return None

    def _log_connection_failure(self, error, connected, control_ready):
        if connected and not control_ready and not isinstance(error, OSError):
            message = (
                "Rover control initialization failed. "
                "Starting a new attempt."
            )
            self.logger.error(
                "{0}: {1}. Retrying in {2:.1f} seconds.".format(
                    message, error, self.connection_retry_seconds
                )
            )
            component = self._initialization_failure_component(error)
            self.status_led_port.set_fault("control_initialization", True)
            self._publish_startup_progress(
                "{0} initialization failed. Retrying in {1:.1f} s.".format(
                    component, self.connection_retry_seconds
                ),
                display_message=(
                    "{0}\ninitialization\nfailed. Retrying\nin {1:.1f} s."
                ).format(component, self.connection_retry_seconds),
                error_alert=True
            )
            return
        if connected:
            message = (
                "Joystick Bluetooth connection lost. "
                "Starting a new search."
            )
        else:
            message = (
                "Joystick still not found. Starting a new search."
            )
        self.logger.warning(
            "{0}: {1}. Retrying in {2:.1f} seconds.".format(
                message, error, self.connection_retry_seconds
            )
        )
        self._notify_joystick_connection_error(message)

    @staticmethod
    def _initialization_failure_component(error):
        """Returns the operator-facing component affected by startup failure."""
        normalized = str(error or "").lower()
        if ("motor" in normalized or
                any(port in normalized for port in (
                    "outa", "outb", "outc", "outd"))):
            return "Motor"
        if any(marker in normalized for marker in (
                "sensor", "gyro", "gyroscope", "ultrasonic",
                "infrared", "touch", "color")):
            return "Sensor"
        if any(marker in normalized for marker in (
                "joystick", "axis", "evdev")):
            return "Joystick"
        return "Rover"

    def _publish_startup_progress(
            self, message, display_message=None, error_alert=False):
        """Publishes one startup step to the log and operator LCD."""
        self.logger.status(message)
        operator_message = (
            message if display_message is None else display_message
        )
        try:
            if error_alert:
                show_error = getattr(
                    self.startup_progress_port, "show_startup_error", None
                )
                if callable(show_error):
                    show_error(operator_message)
                    return
            self.startup_progress_port.show_startup_progress(operator_message)
        except Exception as error:
            self.logger.error(
                "Unable to update startup progress screen: {0}".format(
                    error
                )
            )

    def _notify_joystick_connection_error(self, message):
        self.status_led_port.set_fault("bluetooth", True)
        try:
            self.connection_status_port.show_joystick_connection_error(
                message,
                self.connection_retry_seconds
            )
        except Exception as error:
            self.logger.error(
                "Unable to update Bluetooth error screen: {0}".format(
                    error
                )
            )

    def _notify_joystick_connected(self, device_name):
        clear_faults = getattr(self.status_led_port, "clear_faults", None)
        if callable(clear_faults):
            # Reaching this point means the joystick is open, the manual motor
            # session was acquired successfully, all configured motors were
            # connected, and the traction axes are neutral. Clear every
            # recoverable LOCAL + MANUAL fault atomically before restoring the
            # normal status screen.
            clear_faults("bluetooth", "control_initialization", "motor")
        else:
            self.status_led_port.set_fault("bluetooth", False)
            self.status_led_port.set_fault("control_initialization", False)
            self.status_led_port.set_fault("motor", False)
        try:
            self.connection_status_port.show_joystick_connected(device_name)
        except Exception as error:
            self.logger.error(
                "Unable to restore EV3 status screen: {0}".format(error)
            )

    def _cleanup_connection(self):
        self._stop_all()
        self._release_manual_session(stop=True)
        try:
            self.joystick_port.close()
        except Exception as error:
            self.logger.error(
                "Unable to close joystick input: {0}".format(error)
            )
        with self._state_lock:
            self._reset_input_state_locked()
            self._require_neutral_locked(require_all_axes=True)

    def process_event_batch(self, events):
        """Processes one bounded joystick cycle through the production path.

        Tests and the runtime intentionally share this public contract. Axis
        values are consolidated to their newest value, key presses retain
        safety priority, and at most one traction setpoint is emitted for the
        complete cycle.
        """
        latest_absolute = {}
        pressed_keys = set()
        for event in events or ():
            event_type = event.get("type")
            code = event.get("code")
            if event_type == self.EVENT_ABSOLUTE:
                latest_absolute[code] = event
            elif event_type == self.EVENT_KEY and event.get("value") == 1:
                pressed_keys.add(code)

        if self.stop_button_code in pressed_keys:
            self._stop_all()
            with self._state_lock:
                self._require_neutral_locked(require_all_axes=False)
            return

        if self.field_recenter_button_code in pressed_keys:
            self._handle_field_recenter(latest_absolute)

        if self.drive == Drives.MECANUM:
            self._apply_mecanum_batch(latest_absolute)
        else:
            self._apply_differential_batch(latest_absolute)

    def _handle_field_recenter(self, latest_absolute=None):
        """Redefines FIELD zero from a fresh cached heading when safe."""
        if not self._field_recenter_is_applicable():
            return False

        with self._state_lock:
            if (self.field_recenter_requires_neutral and
                    not self._field_recenter_controls_neutral(
                        latest_absolute
                    )):
                self.logger.error(
                    "FIELD zero not redefined: traction controls must be "
                    "neutral."
                )
                return False

            result = (
                self.field_heading_reference_port
                .set_current_heading_as_zero()
            )
            if not result.get("success"):
                self.logger.error(
                    "FIELD zero not redefined: fresh gyro heading "
                    "unavailable."
                )
                return False

            self._last_mecanum = None
            self.logger.status(
                "FIELD zero redefined from canonical heading "
                "{0:.2f} deg.".format(
                    float(result["reference_heading_deg"])
                )
            )
            return True

    def _field_recenter_is_applicable(self):
        return (
            self.field_recenter_enabled and
            self.drive == Drives.MECANUM and
            self.centric == Centrics.FIELD and
            self.field_heading_reference_port is not None
        )

    def _field_recenter_controls_neutral(self, latest_absolute=None):
        latest_absolute = latest_absolute or {}
        values = {
            self.AXIS_DIRECTION_HORIZONTAL: self._direction_x,
            self.AXIS_DIRECTION_VERTICAL: self._direction_y,
            self.AXIS_ROTATION_HORIZONTAL: self._rotation_x
        }
        for code in tuple(values):
            event = latest_absolute.get(code)
            if event is not None:
                shaped = self._shaped_stick_axis(event.get("value"))
                values[code] = -shaped if code == (
                    self.AXIS_DIRECTION_VERTICAL
                ) else shaped
        return all(value == 0.0 for value in values.values())

    def _apply_differential_batch(self, latest_absolute):
        drive_changed = False
        for code in (
                self.AXIS_DIRECTION_VERTICAL,
                self.AXIS_ROTATION_HORIZONTAL):
            event = latest_absolute.get(code)
            if event is not None:
                self._apply_drive_state_event(event)
                drive_changed = True
        if drive_changed:
            self._update_drive()

        vertical = latest_absolute.get(self.AXIS_AUXILIARY_VERTICAL)
        if vertical is not None:
            self._update_auxiliary(
                self.left_auxiliary_motor_code,
                vertical.get("value"),
                invert=True
            )
        horizontal = latest_absolute.get(self.AXIS_AUXILIARY_HORIZONTAL)
        if horizontal is not None:
            self._update_auxiliary(
                self.right_auxiliary_motor_code,
                horizontal.get("value"),
                invert=True
            )

    def _apply_mecanum_batch(self, latest_absolute):
        changed = False
        horizontal = latest_absolute.get(self.AXIS_DIRECTION_HORIZONTAL)
        vertical = latest_absolute.get(self.AXIS_DIRECTION_VERTICAL)
        rotation = latest_absolute.get(self.AXIS_ROTATION_HORIZONTAL)
        if horizontal is not None:
            self._direction_x = self._shaped_stick_axis(
                horizontal.get("value")
            )
            self._record_axis_neutral(
                self.AXIS_DIRECTION_HORIZONTAL, self._direction_x
            )
            changed = True
        if vertical is not None:
            # Linux evdev uses negative ABS_Y for up and positive for down.
            self._direction_y = -self._shaped_stick_axis(
                vertical.get("value")
            )
            self._record_axis_neutral(
                self.AXIS_DIRECTION_VERTICAL, self._direction_y
            )
            changed = True
        if rotation is not None:
            self._rotation_x = self._shaped_stick_axis(
                rotation.get("value")
            )
            self._record_axis_neutral(
                self.AXIS_ROTATION_HORIZONTAL, self._rotation_x
            )
            changed = True
        if changed:
            self._update_mecanum()

    def _apply_drive_state_event(self, event):
        """Updates in-memory differential translation and rotation state."""
        code = event.get("code")
        value = event.get("value")
        if code == self.AXIS_DIRECTION_VERTICAL:
            self._direction_y = -self._shaped_stick_axis(value)
            self._record_axis_neutral(code, self._direction_y)
        elif code == self.AXIS_ROTATION_HORIZONTAL:
            self._rotation_x = self._shaped_stick_axis(value)
            self._record_axis_neutral(code, self._rotation_x)


    def _shaped_stick_axis(self, value):
        """Applies dead zone and an exponential signed response to one axis."""
        normalized = self._normalized_stick_axis(value)
        if normalized == 0.0:
            return 0.0
        magnitude = self._exponential(
            abs(normalized), self.axis_response_intensity
        )
        return magnitude if normalized > 0 else -magnitude

    def _normalized_stick_axis(self, value):
        """Normalizes the useful axis travel after removing the dead zone."""
        deviation = float(value) - self.axis_center
        magnitude = abs(deviation)
        if magnitude <= self.axis_deadzone:
            return 0.0

        if deviation < 0:
            available_range = float(self.axis_center)
            sign = -1.0
        else:
            available_range = float(self.axis_max - self.axis_center)
            sign = 1.0

        usable_range = max(1.0, available_range - self.axis_deadzone)
        usable_magnitude = magnitude - self.axis_deadzone
        normalized_magnitude = self._clamp(
            usable_magnitude / usable_range, 0.0, 1.0
        )
        return sign * normalized_magnitude

    def _update_drive(self, force_publish=False):
        """Computes normalized differential arcade-drive wheel speeds."""
        with self._state_lock:
            neutral = self._differential_controls_neutral()
            if not self._prepare_after_stop(neutral):
                return

            left_ratio = self._direction_y + self._rotation_x
            right_ratio = self._direction_y - self._rotation_x
            denominator = max(abs(left_ratio), abs(right_ratio), 1.0)
            left_speed = int(round(
                (left_ratio / denominator) * self.max_speed_sp
            ))
            right_speed = int(round(
                (right_ratio / denominator) * self.max_speed_sp
            ))

            setpoint = self._apply_differential_direction(
                left_speed, right_speed
            )
            if force_publish or setpoint != self._last_drive:
                self._last_drive = setpoint
                self._dispatch_drive(*setpoint)
            else:
                self._last_drive = setpoint

    def _update_mecanum(self, force_publish=False):
        """Computes normalized Mecanum wheel speeds in the selected frame."""
        with self._state_lock:
            translation = self._mecanum_translation_vector()
            if translation is None:
                self._handle_field_heading_unavailable_locked()
                return

            if self._field_heading_unavailable:
                self._field_heading_unavailable = False
                self.logger.status(
                    "Fresh gyro heading restored; neutral controls are "
                    "required before FIELD motion resumes."
                )

            neutral = self._mecanum_controls_neutral()
            if not self._prepare_after_stop(neutral):
                return

            x_value, y_value = translation
            rotation = self._rotation_x
            wheel_ratios = self._mecanum_ratios(
                x_value, y_value, rotation
            )
            wheel_ratios = self._apply_mecanum_direction(wheel_ratios)
            setpoint = tuple(
                int(round(self.max_speed_sp * ratio))
                for ratio in wheel_ratios
            )
            if force_publish or setpoint != self._last_mecanum:
                self._last_mecanum = setpoint
                self._dispatch_mecanum(*setpoint)
            else:
                self._last_mecanum = setpoint

    def _traction_axis_codes(self):
        if self.drive == Drives.MECANUM:
            axes = {
                self.AXIS_DIRECTION_HORIZONTAL,
                self.AXIS_DIRECTION_VERTICAL
            }
            axes.add(self.AXIS_ROTATION_HORIZONTAL)
            return axes
        return {
            self.AXIS_DIRECTION_VERTICAL,
            self.AXIS_ROTATION_HORIZONTAL
        }

    def _axis_value(self, code):
        if code == self.AXIS_DIRECTION_HORIZONTAL:
            return self._direction_x
        if code == self.AXIS_DIRECTION_VERTICAL:
            return self._direction_y
        if code == self.AXIS_ROTATION_HORIZONTAL:
            return self._rotation_x
        return 0.0

    def _require_neutral_locked(self, require_all_axes):
        self._neutral_required = True
        axes = self._traction_axis_codes()
        if require_all_axes:
            self._neutral_pending_axes = set(axes)
        else:
            self._neutral_pending_axes = {
                code for code in axes if self._axis_value(code) != 0.0
            }

    def _record_axis_neutral(self, code, value):
        if self._neutral_required and value == 0.0:
            self._neutral_pending_axes.discard(code)

    def _differential_controls_neutral(self):
        return self._direction_y == 0.0 and self._rotation_x == 0.0

    def _mecanum_controls_neutral(self):
        return (
            self._direction_x == 0.0 and
            self._direction_y == 0.0 and
            self._rotation_x == 0.0
        )

    def _prepare_after_stop(self, neutral):
        if not self._neutral_required:
            return True
        if not neutral or self._neutral_pending_axes:
            return False
        self._neutral_required = False
        self._neutral_pending_axes.clear()
        if self._session_id is None:
            self._acquire_manual_session()
        return True

    @staticmethod
    def _mecanum_ratios(x_value, y_value, rotation=0.0):
        """Returns standard Chassis-centric Mecanum wheel ratios.

        The denominator follows the supplied FTC reference implementation:
        ``max(abs(y) + abs(x) + abs(rx), 1)``. This keeps every output in
        ``[-1, 1]`` while preserving the ratio among translation and rotation.
        """
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

    def _mecanum_translation_vector(self):
        """Returns the joystick vector in the selected Mecanum reference."""
        if self.centric == Centrics.CHASSIS:
            return (
                self._direction_x * self.mecanum_strafe_compensation,
                self._direction_y
            )

        heading_deg = self.heading_query_port.get_heading_deg()
        if heading_deg is None:
            return None

        # The injected query publishes the operational FIELD heading. Its
        # source remains a cached canonical gyro sample; no hardware I/O occurs
        # on this joystick path.
        heading_rad = math.radians(float(heading_deg))
        cosine = math.cos(heading_rad)
        sine = math.sin(heading_rad)
        rotated_x = (
            self._direction_x * cosine - self._direction_y * sine
        )
        rotated_y = (
            self._direction_x * sine + self._direction_y * cosine
        )
        return (
            rotated_x * self.mecanum_strafe_compensation,
            rotated_y
        )

    def _handle_field_heading_unavailable_locked(self):
        """Stops FIELD motion once and requires neutral after gyro recovery."""
        if self._field_heading_unavailable:
            return
        self._field_heading_unavailable = True
        self._stop_all()
        self._require_neutral_locked(require_all_axes=False)
        self.logger.error(
            "Fresh gyro heading unavailable; FIELD traction stopped."
        )


    def _apply_differential_direction(self, left_speed, right_speed):
        """Applies front convention and Differential mechanical direction."""
        if self.front == Fronts.TAIL:
            left_output = -int(right_speed)
            right_output = -int(left_speed)
        else:
            left_output = int(left_speed)
            right_output = int(right_speed)

        if self.differential_mode == DifferentialModes.R_BOGIE:
            return -left_output, -right_output
        return left_output, right_output

    def _apply_mecanum_direction(self, wheel_ratios):
        """Applies only the operator-facing front/rear convention.

        Physical motor polarity and the front Large-motor gear inversion are
        configuration concerns and are deliberately not encoded here.
        """
        front_left, rear_left, front_right, rear_right = wheel_ratios

        if self.front == Fronts.NOSE:
            return wheel_ratios

        # TAIL rotates the operator translation frame by 180 degrees while
        # preserving the requested rotational direction.
        return (
            -rear_right,
            -front_right,
            -rear_left,
            -front_left
        )

    def _dispatch_drive(self, left_speed, right_speed):
        if self._session_id is None:
            return
        try:
            result = self.manual_drive_port.apply_drive_setpoint(
                self._session_id, left_speed, right_speed
            )
            self._handle_drive_result(result)
        except Exception as error:
            self.logger.error(
                "Joystick direct motor dispatch failed: {0}".format(error)
            )
            self._terminate_manual_session("dispatch_failed")

    def _dispatch_mecanum(self, front_left, rear_left, front_right, rear_right):
        if self._session_id is None:
            return
        try:
            result = self.manual_drive_port.apply_mecanum_setpoint(
                self._session_id,
                front_left,
                rear_left,
                front_right,
                rear_right
            )
            self._handle_drive_result(result)
        except Exception as error:
            self.logger.error(
                "Joystick Mecanum dispatch failed: {0}".format(error)
            )
            self._terminate_manual_session("dispatch_failed")

    def _handle_drive_result(self, result):
        if isinstance(result, dict) and result.get("session_invalid"):
            self._invalidate_manual_session(
                result.get("reason") or "session_invalid"
            )
            return
        if isinstance(result, dict) and not result.get("success", True):
            error = result.get("error") or "Motor hardware rejected the setpoint."
            failed_motor_code = result.get("failed_motor_code")
            if failed_motor_code:
                error = "{0}: {1}".format(failed_motor_code, error)
            self.logger.error(
                "Joystick drive setpoint was rejected: {0}".format(error)
            )
            self._terminate_manual_session("hardware_rejected")

    def _update_auxiliary(self, motor_code, value, invert=False):
        speed = 0
        if value != 0:
            direction = -value if invert else value
            speed = self.auxiliary_speed_sp * (1 if direction > 0 else -1)
        if self._neutral_required or self._session_id is None:
            return

        self._auxiliary_state[motor_code] = speed
        result = self.manual_drive_port.apply_auxiliary_setpoint(
            self._session_id, motor_code, speed
        )
        if isinstance(result, dict) and result.get("session_invalid"):
            self._invalidate_manual_session("session_invalid")
        elif isinstance(result, dict) and not result.get("success", True):
            self._terminate_manual_session("hardware_rejected")

    def _acquire_manual_session(self):
        session_id = uuid.uuid4().hex
        result = self.manual_drive_port.acquire(
            session_id,
            motor_codes=(
                self.left_auxiliary_motor_code,
                self.right_auxiliary_motor_code
            )
        )
        if isinstance(result, dict) and not result.get("success", False):
            raise RuntimeError(
                result.get("error") or "Unable to acquire manual control."
            )
        self._session_id = session_id

    def _release_manual_session(self, stop=False):
        session_id = self._session_id
        self._session_id = None
        self._release_session_id(session_id, stop)

    def _release_session_id(self, session_id, stop):
        if session_id is None:
            return
        try:
            self.manual_drive_port.release(session_id, stop=stop)
        except Exception as error:
            self.logger.error(
                "Unable to release joystick control session: {0}".format(error)
            )

    def _terminate_manual_session(self, reason):
        with self._state_lock:
            session_id = self._session_id
            if self._neutral_required and session_id is None:
                return
            self._require_neutral_locked(require_all_axes=False)
            self._reset_motion_state_locked()
            self._session_id = None

        self._stop_all()
        self._release_session_id(session_id, stop=True)
        self.logger.error(
            "Joystick manual session terminated ({0}); "
            "return controls to neutral.".format(reason)
        )

    def _invalidate_manual_session(self, reason):
        with self._state_lock:
            if self._neutral_required and self._session_id is None:
                return
            session_id = self._session_id
            self._session_id = None
            self._require_neutral_locked(require_all_axes=False)
            self._reset_motion_state_locked()

        self._stop_all()
        self._release_session_id(session_id, stop=True)
        self.logger.error(
            "Joystick manual session invalidated ({0}); "
            "return controls to neutral.".format(reason)
        )

    def _reset_motion_state_locked(self):
        self._last_drive = (0, 0)
        self._last_mecanum = (0, 0, 0, 0)
        for motor_code in self._auxiliary_state:
            self._auxiliary_state[motor_code] = 0

    def _reset_input_state_locked(self):
        self._direction_x = 0.0
        self._direction_y = 0.0
        self._rotation_x = 0.0
        self._startup_axis_raw_values = {}
        self._reset_motion_state_locked()

    def _stop_all(self):
        try:
            self.manual_drive_port.emergency_stop()
        except Exception as error:
            self.logger.error(
                "Unable to stop joystick-controlled motors: {0}".format(error)
            )
        with self._state_lock:
            self._reset_motion_state_locked()

    @staticmethod
    def _validate_operation_mode(operation_mode):
        resolved_mode = coerce_operation_mode(operation_mode)
        if not resolved_mode.is_local_manual():
            raise ValueError(
                "Joystick control requires a LOCAL + MANUAL operation mode."
            )
        return resolved_mode

    def _validate_field_control_dependencies(self):
        if (self.drive == Drives.MECANUM and
                self.centric == Centrics.FIELD and
                self.heading_query_port is None):
            raise ValueError(
                "FIELD-centric Mecanum control requires HeadingQueryPort."
            )

        if (self.drive == Drives.MECANUM and
                self.centric == Centrics.FIELD and
                self.field_recenter_enabled and
                self.field_heading_reference_port is None):
            raise ValueError(
                "FIELD recenter requires "
                "FieldHeadingReferenceCommandPort."
            )

    @classmethod
    def _validate_neutral_timing(
            cls, stability_seconds, poll_seconds):
        stability = cls._validate_positive_seconds(
            "neutral_stability_seconds", stability_seconds
        )
        poll = cls._validate_positive_seconds(
            "neutral_poll_seconds", poll_seconds
        )
        if poll > stability:
            raise ValueError(
                "neutral_poll_seconds must not exceed "
                "neutral_stability_seconds."
            )
        return stability, poll

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
    def _validate_positive_seconds(name, value):
        seconds = float(value)
        if not math.isfinite(seconds) or seconds <= 0.0:
            raise ValueError(
                "{0} must be finite and greater than zero.".format(name)
            )
        return seconds

    @staticmethod
    def _validate_response_intensity(axis_response_intensity):
        intensity = float(axis_response_intensity)
        if not math.isfinite(intensity) or intensity <= 0.0:
            raise ValueError(
                "axis_response_intensity must be finite and greater "
                "than zero."
            )
        return intensity

    @staticmethod
    def _exponential(value, intensity):
        value = max(0.0, min(1.0, float(value)))
        return (math.exp(intensity * value) - 1.0) / (
            math.exp(intensity) - 1.0
        )

    @staticmethod
    def _clamp(value, minimum, maximum):
        return max(minimum, min(maximum, value))
