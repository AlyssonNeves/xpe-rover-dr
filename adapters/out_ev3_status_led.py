#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 status LED adapter driven by Rover operational state."""

import glob
import os
import threading

from app.operation_mode_service import Commands, Controls
from ports.runtime_component_port import RuntimeComponentPort
from ports.status_led_port import StatusLedPort

class NullStatusLedLogger(object):
    """No-op logger for standalone adapter use and unit tests."""

    @staticmethod
    def status(message):
        del message

    @staticmethod
    def error(message):
        del message


class Ev3StatusLedAdapter(StatusLedPort, RuntimeComponentPort):
    """Maps Rover mode and faults to synchronized EV3 heartbeat LEDs.

    Priority is RED for any active fault, YELLOW for REMOTE or LOCAL +
    AUTOMATIC, and GREEN for LOCAL + MANUAL. Blinking remains implemented by
    the Linux ``heartbeat`` trigger; Python only selects trigger channels and
    brightness.
    """

    COLOR_GREEN = "GREEN"
    COLOR_YELLOW = "YELLOW"
    COLOR_RED = "RED"
    YELLOW_RED_BRIGHTNESS = 25
    DEFAULT_MAX_BRIGHTNESS = 255
    POLL_SECONDS = 0.25

    def __init__(self, operation_mode_service=None, motor_query_port=None,
                 led_root="/sys/class/leds", poll_seconds=None, logger=None):
        self._operation_mode_service = operation_mode_service
        self._motor_query_port = motor_query_port
        self._led_root = led_root
        self._poll_seconds = float(
            self.POLL_SECONDS if poll_seconds is None else poll_seconds
        )
        self._faults = set()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None
        self._last_color = None
        self._logger = logger or NullStatusLedLogger()

    def set_motor_query_port(self, motor_query_port):
        """Injects the canonical motor query port used for health checks."""
        self._motor_query_port = motor_query_port

    def set_fault(self, source, active=True):
        """Activates or clears a fault and immediately refreshes the LEDs."""
        source_name = str(source or "operational")
        changed = False
        with self._lock:
            before = source_name in self._faults
            if active:
                self._faults.add(source_name)
            else:
                self._faults.discard(source_name)
            changed = before != bool(active)
        if changed:
            self._log_fault_state()
        self.refresh()

    def clear_faults(self, *sources):
        """Clears related faults atomically and forces one physical refresh.

        Fault recovery is a state transition that must be reflected on the
        brick even if a previous kernel/brickrun write left the physical LEDs
        different from the adapter's cached color.
        """
        changed = False
        with self._lock:
            for source in sources:
                source_name = str(source or "operational")
                if source_name in self._faults:
                    changed = True
                self._faults.discard(source_name)
        if changed:
            self._log_fault_state()
        self.refresh(force=True)

    def prepare_start(self):
        """Applies the correct indication before worker threads start."""
        self._refresh_motor_fault()
        self.refresh()

    def start(self):
        """Starts lightweight motor-health observation when applicable."""
        self.prepare_start()
        if self._motor_query_port is None:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="Ev3StatusLedThread"
        )
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """Stops status observation; brickrun restores its LEDs on process exit."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def refresh(self, force=False):
        """Recomputes and applies the current highest-priority LED color."""
        with self._lock:
            color = self._resolve_color_locked()
        return self._apply_color(color, force=force)

    def _run(self):
        while not self._stop_event.wait(self._poll_seconds):
            self._refresh_motor_fault()
            self.refresh()

    def _refresh_motor_fault(self):
        if self._motor_query_port is None:
            return
        try:
            motors = self._motor_query_port.read_all_motors() or []
        except Exception:
            self.set_fault("motor", True)
            return
        unavailable = any(
            self._motor_has_fault(motor)
            for motor in motors
        )
        recovered = False
        with self._lock:
            if unavailable:
                self._faults.add("motor")
            else:
                recovered = "motor" in self._faults
                self._faults.discard("motor")
        if recovered:
            self.refresh(force=True)


    @staticmethod
    def _motor_has_fault(motor):
        """Returns True only for an evidenced motor hardware failure.

        A bare DISCONNECTED/RETRYING state can be transient while the direct
        LOCAL + MANUAL repository is still being initialized. Treating that
        state alone as a fault can latch the status LED red even though the
        motor subsequently connects normally. Real disconnects published by
        the EV3 repository include ``hardware_error``; backend-wide failures
        are represented explicitly by HARDWARE_UNAVAILABLE/FAILED.
        """
        if not bool(motor.get("hardware_enabled", True)):
            return False
        if bool(motor.get("connected", False)):
            return False
        if motor.get("hardware_error"):
            return True
        return motor.get("lifecycle_state") in (
            "HARDWARE_UNAVAILABLE",
            "FAILED"
        )

    def _resolve_color_locked(self):
        if self._faults:
            return self.COLOR_RED
        mode = self._get_mode()
        if mode is None:
            return self.COLOR_GREEN
        if mode.command == Commands.REMOTE:
            return self.COLOR_YELLOW
        if mode.control == Controls.AUTOMATIC:
            return self.COLOR_YELLOW
        return self.COLOR_GREEN

    def _get_mode(self):
        if self._operation_mode_service is None:
            return None
        try:
            return self._operation_mode_service.get_mode()
        except (AttributeError, RuntimeError, ValueError):
            return None

    def _apply_color(self, color, force=False):
        with self._lock:
            if color == self._last_color and not force:
                return True
            channels = self._find_channels()
            if not channels["green"] and not channels["red"]:
                return False
            try:
                self._disable_channels(channels)
                self._enable_color(channels, color)
            except (IOError, OSError) as error:
                self._logger.error(
                    "Unable to apply EV3 status LED color {0}: {1}".format(
                        color, error
                    )
                )
                return False
            changed = color != self._last_color
            self._last_color = color
            if changed or force:
                self._log_applied_color(color)
            return True

    def _log_fault_state(self):
        with self._lock:
            faults = sorted(self._faults)
        label = ", ".join(faults) if faults else "none"
        self._logger.status(
            "Status LED faults: {0}.".format(label)
        )

    def _log_applied_color(self, color):
        with self._lock:
            faults = sorted(self._faults)
        label = ", ".join(faults) if faults else "none"
        self._logger.status(
            "Status LEDs: {0} heartbeat (faults={1}).".format(
                color, label
            )
        )

    def _find_channels(self):
        """Returns only the EV3 brick status LED channels.

        Bluetooth/USB HID devices can also expose entries under
        ``/sys/class/leds`` (for example a DualShock ``*:green`` LED).
        Broad ``*green*``/``*red*`` globs would therefore try to control
        device LEDs that do not belong to the EV3 brick and may not be
        writable by the ``robot`` user.
        """
        return {
            "green": sorted(glob.glob(os.path.join(
                self._led_root, "*:green:brick-status", "trigger"
            ))),
            "red": sorted(glob.glob(os.path.join(
                self._led_root, "*:red:brick-status", "trigger"
            )))
        }

    def _disable_channels(self, channels):
        for trigger_path in channels["green"] + channels["red"]:
            self._write(trigger_path, "none")
            self._write(self._brightness_path(trigger_path), "0")

    def _enable_color(self, channels, color):
        if color == self.COLOR_GREEN:
            self._enable_channels(channels["green"], None)
            return
        if color == self.COLOR_RED:
            self._enable_channels(channels["red"], None)
            return
        self._enable_channels(channels["green"], None)
        self._enable_channels(
            channels["red"], self.YELLOW_RED_BRIGHTNESS
        )

    def _enable_channels(self, trigger_paths, brightness):
        for trigger_path in trigger_paths:
            self._write(trigger_path, "heartbeat")
        for trigger_path in trigger_paths:
            brightness_path = self._brightness_path(trigger_path)
            maximum = self._max_brightness(brightness_path)
            value = maximum
            if brightness is not None:
                value = int(round(
                    maximum * float(brightness) / self.DEFAULT_MAX_BRIGHTNESS
                ))
            self._write(brightness_path, str(value))

    def _max_brightness(self, brightness_path):
        max_path = os.path.join(os.path.dirname(brightness_path), "max_brightness")
        try:
            with open(max_path, "r") as value_file:
                return int(value_file.read().strip())
        except (IOError, OSError, TypeError, ValueError):
            return self.DEFAULT_MAX_BRIGHTNESS

    @staticmethod
    def _brightness_path(trigger_path):
        return os.path.join(os.path.dirname(trigger_path), "brightness")

    @staticmethod
    def _write(path, value):
        with open(path, "w") as output_file:
            output_file.write(str(value))
