#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Linux evdev input adapter for the local manual joystick."""

import select

from ports.joystick_port import JoystickPort


class EvdevJoystickAdapter(JoystickPort):
    """Reads one named Linux ``/dev/input/event*`` game controller.

    This first evdev integration intentionally limits itself to device
    discovery, event reading and resource release. Bluetooth connection and
    reconnection policies are introduced by later Rover-DR increments.
    """

    def __init__(self, device_name="Wireless Controller", evdev_module=None,
                 select_function=None):
        self.device_name = str(device_name or "").strip()
        if not self.device_name:
            raise ValueError("device_name must not be empty.")
        self.evdev_module = evdev_module
        self.select_function = select_function or select.select
        self.device = None

    def open(self):
        """Discovers and opens the configured evdev controller."""
        self._load_evdev_module()
        self.close()

        for path in self.evdev_module.list_devices():
            try:
                candidate = self.evdev_module.InputDevice(path)
            except (IOError, OSError):
                continue

            if candidate.name == self.device_name:
                self.device = candidate
                return candidate.name
            candidate.close()

        raise RuntimeError(
            "Joystick '{0}' was not found in Linux evdev.".format(
                self.device_name
            )
        )

    def read_event(self, timeout_seconds=None):
        """Returns the next evdev event normalized as a small dictionary."""
        if self.device is None:
            raise RuntimeError("Joystick device is not open.")

        timeout = self._normalize_timeout(timeout_seconds)
        readable, _, _ = self.select_function(
            [self.device.fd], [], [], timeout
        )
        if not readable:
            return None

        event = self.device.read_one()
        if event is None:
            return None
        return {
            "type": int(event.type),
            "code": int(event.code),
            "value": int(event.value)
        }

    def close(self):
        """Closes the current Linux input device, when one is active."""
        device = self.device
        self.device = None
        if device is not None:
            device.close()

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
