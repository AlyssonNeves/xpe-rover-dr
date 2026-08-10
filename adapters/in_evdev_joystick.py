#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Linux evdev input adapter for an automatically connected Bluetooth joystick."""

import select
import subprocess
import threading
import time

from ports.joystick_port import JoystickPort


class EvdevJoystickAdapter(JoystickPort):
    """Discovers, connects and reads one named Linux Bluetooth controller.

    Device selection in this increment intentionally remains name-based.
    Capability-aware selection of same-name HID nodes is introduced later in
    S02.24. The responsibility here is connection lifecycle: use an already
    exposed evdev node when possible, otherwise ask BlueZ to connect the
    configured address and wait for the node to appear.
    """

    BLUETOOTH_POLL_SECONDS = 0.1

    def __init__(self, device_name="Wireless Controller", device_address="",
                 auto_connect=True, connection_timeout_seconds=10.0,
                 discovery_poll_seconds=0.25, evdev_module=None,
                 select_function=None, popen_factory=None,
                 monotonic_clock=None):
        self.device_name = str(device_name or "").strip()
        if not self.device_name:
            raise ValueError("device_name must not be empty.")
        self.device_address = str(device_address or "").strip()
        self.auto_connect = bool(auto_connect)
        self.connection_timeout_seconds = max(
            0.1, float(connection_timeout_seconds)
        )
        self.discovery_poll_seconds = max(
            0.01, float(discovery_poll_seconds)
        )
        self.evdev_module = evdev_module
        self.select_function = select_function or select.select
        self.popen_factory = popen_factory or subprocess.Popen
        self.monotonic_clock = monotonic_clock or time.monotonic
        self.device = None
        self._connection_cancel_event = threading.Event()
        self._connection_process = None
        self._connection_lock = threading.RLock()

    def is_available(self):
        """Returns whether the configured joystick is already exposed."""
        self._load_evdev_module()
        candidate = self._find_named_device()
        if candidate is None:
            return False
        candidate.close()
        return True

    def open(self):
        """Opens the joystick, requesting a BlueZ connection when required."""
        self._connection_cancel_event.clear()
        self._load_evdev_module()
        self._close_device()

        candidate = self._find_named_device()
        if candidate is not None:
            return self._activate_device(candidate)

        if not self.auto_connect:
            raise RuntimeError(
                "Joystick '{0}' was not found and automatic Bluetooth "
                "connection is disabled.".format(self.device_name)
            )
        if not self.device_address:
            raise RuntimeError(
                "Joystick '{0}' was not found and no Bluetooth "
                "device_address is configured.".format(self.device_name)
            )

        deadline = self.monotonic_clock() + self.connection_timeout_seconds
        self._execute_bluetooth_connect(deadline)
        candidate = self._wait_for_named_device(deadline)
        if candidate is None:
            raise RuntimeError(
                "Joystick '{0}' did not appear in Linux evdev after "
                "connecting Bluetooth device {1}.".format(
                    self.device_name, self.device_address
                )
            )
        return self._activate_device(candidate)

    def read_event(self, timeout_seconds=None):
        """Returns the next evdev event normalized as a small dictionary."""
        if self.device is None:
            raise RuntimeError("Joystick device is not open.")

        timeout = self._normalize_timeout(timeout_seconds)
        try:
            readable, _, exceptional = self.select_function(
                [self.device.fd], [], [self.device.fd], timeout
            )
        except (IOError, OSError) as error:
            raise self._connection_lost(error)

        if exceptional:
            raise self._connection_lost(
                OSError("evdev descriptor reported an exceptional state")
            )
        if not readable:
            return None

        try:
            event = self.device.read_one()
        except (IOError, OSError) as error:
            raise self._connection_lost(error)
        if event is None:
            return None
        return {
            "type": int(event.type),
            "code": int(event.code),
            "value": int(event.value)
        }

    def close(self):
        """Cancels connection work and closes the current input device."""
        self._connection_cancel_event.set()
        self._cancel_connection_process()
        self._close_device()

    def _find_named_device(self):
        """Returns the first evdev node whose display name matches."""
        for path in self.evdev_module.list_devices():
            try:
                candidate = self.evdev_module.InputDevice(path)
            except (IOError, OSError):
                continue
            if candidate.name == self.device_name:
                return candidate
            candidate.close()
        return None

    def _activate_device(self, candidate):
        self.device = candidate
        return candidate.name

    def _execute_bluetooth_connect(self, deadline):
        """Runs ``bluetoothctl connect <MAC>`` within the shared timeout."""
        remaining = max(0.0, deadline - self.monotonic_clock())
        if remaining <= 0.0:
            raise RuntimeError("Bluetooth joystick connection timed out.")
        try:
            process = self.popen_factory(
                ["bluetoothctl", "connect", self.device_address],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
        except (IOError, OSError) as error:
            raise RuntimeError(
                "Unable to execute bluetoothctl: {0}".format(error)
            )

        with self._connection_lock:
            self._connection_process = process
        output = ""
        try:
            while process.poll() is None:
                if self._connection_cancel_event.is_set():
                    self._terminate_process(process)
                    raise RuntimeError(
                        "Bluetooth joystick connection attempt was cancelled."
                    )
                remaining = deadline - self.monotonic_clock()
                if remaining <= 0.0:
                    output = self._terminate_process(process)
                    raise RuntimeError(
                        "Bluetooth connection to {0} timed out after {1:.1f} "
                        "seconds. bluetoothctl: {2}".format(
                            self.device_address,
                            self.connection_timeout_seconds,
                            self._clean_process_output(output) or
                            "no diagnostic output"
                        )
                    )
                self._connection_cancel_event.wait(
                    min(self.BLUETOOTH_POLL_SECONDS, remaining)
                )
            output = self._collect_process_output(process)
        finally:
            with self._connection_lock:
                if self._connection_process is process:
                    self._connection_process = None

        if process.returncode != 0:
            raise RuntimeError(
                "bluetoothctl could not connect {0}: {1}".format(
                    self.device_address,
                    self._clean_process_output(output) or "unknown error"
                )
            )
        return output

    def _wait_for_named_device(self, deadline):
        while not self._connection_cancel_event.is_set():
            candidate = self._find_named_device()
            if candidate is not None:
                return candidate
            remaining = deadline - self.monotonic_clock()
            if remaining <= 0.0:
                return None
            self._connection_cancel_event.wait(
                min(self.discovery_poll_seconds, remaining)
            )
        raise RuntimeError("Bluetooth joystick connection attempt was cancelled.")

    @staticmethod
    def _clean_process_output(output):
        return " ".join(str(output or "").strip().split())

    @staticmethod
    def _collect_process_output(process):
        try:
            output, _ = process.communicate()
            return output or ""
        except (IOError, OSError, ValueError):
            return ""

    @classmethod
    def _terminate_process(cls, process):
        if process.poll() is not None:
            return cls._collect_process_output(process)
        try:
            process.terminate()
            output, _ = process.communicate()
            return output or ""
        except (IOError, OSError, ValueError):
            try:
                process.kill()
            except (IOError, OSError, AttributeError):
                pass
            return cls._collect_process_output(process)

    def _cancel_connection_process(self):
        with self._connection_lock:
            process = self._connection_process
        if process is not None:
            self._terminate_process(process)

    def _close_device(self):
        device = self.device
        self.device = None
        if device is not None:
            device.close()

    def _connection_lost(self, error):
        """Releases the stale descriptor and returns a clear disconnect error."""
        try:
            self._close_device()
        except (IOError, OSError):
            self.device = None
        return OSError(
            "Bluetooth joystick connection lost: {0}".format(error)
        )

    def _load_evdev_module(self):
        if self.evdev_module is not None:
            return
        try:
            import evdev
        except ImportError as error:
            raise RuntimeError(
                "python-evdev is not available: {0}".format(error)
            )
        self.evdev_module = evdev

    @staticmethod
    def _normalize_timeout(timeout_seconds):
        if timeout_seconds is None:
            return None
        return max(0.0, float(timeout_seconds))
