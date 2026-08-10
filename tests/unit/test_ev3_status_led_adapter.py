#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the centralized EV3 operational status LED adapter."""

import os
import shutil
import tempfile
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from adapters.out_ev3_status_led import Ev3StatusLedAdapter
from app.operation_mode_service import (
    Commands,
    Controls,
    OperationModeService
)


class Ev3StatusLedAdapterTestCase(unittest.TestCase):
    def setUp(self):
        self.led_root = tempfile.mkdtemp(prefix="rover-led-")
        # Windows rejects ':' in directory names, while real EV3 sysfs LED
        # channel names contain it. Use portable backing directories and mock
        # only glob discovery; the adapter still receives normal file paths.
        self.green_led_names = (
            "led0-green-brick-status",
            "led1-green-brick-status"
        )
        self.red_led_names = (
            "led0-red-brick-status",
            "led1-red-brick-status"
        )
        for name in self.green_led_names + self.red_led_names:
            led_dir = os.path.join(self.led_root, name)
            os.makedirs(led_dir)
            self._write(os.path.join(led_dir, "trigger"), "none")
            self._write(os.path.join(led_dir, "brightness"), "0")
            self._write(os.path.join(led_dir, "max_brightness"), "255")
        self._glob_patcher = mock.patch(
            "adapters.out_ev3_status_led.glob.glob",
            side_effect=self._portable_led_glob
        )
        self._glob_mock = self._glob_patcher.start()

    def tearDown(self):
        self._glob_patcher.stop()
        shutil.rmtree(self.led_root)

    def test_local_manual_is_green_heartbeat(self):
        adapter = self._adapter(Commands.LOCAL, Controls.MANUAL)
        self.assertTrue(adapter.refresh())
        self._assert_color(255, 0)

    def test_remote_is_yellow_heartbeat(self):
        adapter = self._adapter(Commands.REMOTE, Controls.MANUAL)
        self.assertTrue(adapter.refresh())
        self._assert_color(255, 25)

    def test_local_automatic_is_yellow_heartbeat(self):
        adapter = self._adapter(Commands.LOCAL, Controls.AUTOMATIC)
        self.assertTrue(adapter.refresh())
        self._assert_color(255, 25)

    def test_fault_overrides_mode_with_red_and_recovers(self):
        adapter = self._adapter(Commands.REMOTE, Controls.MANUAL)
        adapter.set_fault("bluetooth", True)
        self._assert_color(0, 255)
        adapter.set_fault("bluetooth", False)
        self._assert_color(255, 25)


    def test_uninitialized_motor_state_does_not_raise_false_fault(self):
        motor_query = mock.Mock()
        motor_query.read_all_motors.return_value = [{
            "code": "LLM",
            "hardware_enabled": True,
            "connected": False,
            "hardware_error": None,
            "lifecycle_state": "DISCONNECTED"
        }]
        adapter = self._adapter(
            Commands.LOCAL,
            Controls.MANUAL,
            motor_query_port=motor_query
        )
        adapter.prepare_start()
        self._assert_color(255, 0)

    def test_bluetooth_recovery_is_not_blocked_by_transient_motor_state(self):
        motor_query = mock.Mock()
        motor_query.read_all_motors.return_value = [{
            "code": "LLM",
            "hardware_enabled": True,
            "connected": False,
            "hardware_error": None,
            "lifecycle_state": "DISCONNECTED"
        }]
        adapter = self._adapter(
            Commands.LOCAL,
            Controls.MANUAL,
            motor_query_port=motor_query
        )
        adapter.prepare_start()
        adapter.set_fault("bluetooth", True)
        self._assert_color(0, 255)

        adapter.clear_faults("bluetooth", "control_initialization")
        self._assert_color(255, 0)

    def test_ready_recovery_clears_bluetooth_initialization_and_motor_faults(self):
        adapter = self._adapter(Commands.LOCAL, Controls.MANUAL)
        adapter.set_fault("bluetooth", True)
        adapter.set_fault("control_initialization", True)
        adapter.set_fault("motor", True)
        self._assert_color(0, 255)

        adapter.clear_faults(
            "bluetooth", "control_initialization", "motor"
        )

        self._assert_color(255, 0)

    def test_fault_clear_forces_physical_led_rewrite(self):
        adapter = self._adapter(Commands.LOCAL, Controls.MANUAL)
        adapter.refresh()
        self._assert_color(255, 0)

        # Simulates an external sysfs writer changing the physical LEDs while
        # the adapter still has GREEN cached as its intended color.
        for name in self.green_led_names:
            self._write(os.path.join(self.led_root, name, "trigger"), "none")
            self._write(os.path.join(self.led_root, name, "brightness"), "0")
        for name in self.red_led_names:
            self._write(os.path.join(self.led_root, name, "trigger"), "heartbeat")
            self._write(os.path.join(self.led_root, name, "brightness"), "255")

        adapter.clear_faults("bluetooth", "control_initialization", "motor")

        self._assert_color(255, 0)


    def test_ignores_non_brick_leds_exposed_by_bluetooth_devices(self):
        device_name = "0005-054C-09CC.0017-green"
        device_led = os.path.join(self.led_root, device_name)
        os.makedirs(device_led)
        self._write(os.path.join(device_led, "trigger"), "none")
        self._write(os.path.join(device_led, "brightness"), "0")
        self._write(os.path.join(device_led, "max_brightness"), "255")

        adapter = self._adapter(Commands.LOCAL, Controls.MANUAL)
        channels = adapter._find_channels()

        self.assertEqual(2, len(channels["green"]))
        self.assertEqual(2, len(channels["red"]))
        self.assertFalse(any(
            device_name in path
            for path in channels["green"] + channels["red"]
        ))
        self.assertIn(
            mock.call(os.path.join(
                self.led_root, "*:green:brick-status", "trigger"
            )),
            self._glob_mock.call_args_list
        )
        self.assertIn(
            mock.call(os.path.join(
                self.led_root, "*:red:brick-status", "trigger"
            )),
            self._glob_mock.call_args_list
        )
        self.assertTrue(adapter.refresh(force=True))
        self.assertEqual("none", self._read(device_name, "trigger"))

    def test_motor_disconnect_sets_red_and_reconnection_restores_mode(self):
        motor_query = mock.Mock()
        motor_query.read_all_motors.return_value = [{
            "code": "LLM",
            "hardware_enabled": True,
            "connected": False,
            "hardware_error": "motor is disconnected",
            "lifecycle_state": "DISCONNECTED"
        }]
        adapter = self._adapter(
            Commands.LOCAL,
            Controls.MANUAL,
            motor_query_port=motor_query
        )
        adapter.prepare_start()
        self._assert_color(0, 255)

        motor_query.read_all_motors.return_value = [{
            "code": "LLM",
            "hardware_enabled": True,
            "connected": True
        }]
        adapter._refresh_motor_fault()
        adapter.refresh()
        self._assert_color(255, 0)

    def _adapter(self, command, control, motor_query_port=None):
        mode_service = OperationModeService(command=command, control=control)
        return Ev3StatusLedAdapter(
            operation_mode_service=mode_service,
            motor_query_port=motor_query_port,
            led_root=self.led_root
        )

    def _assert_color(self, green_brightness, red_brightness):
        for name in self.green_led_names:
            self.assertEqual(
                str(green_brightness), self._read(name, "brightness")
            )
            expected = "heartbeat" if green_brightness else "none"
            self.assertEqual(expected, self._read(name, "trigger"))
        for name in self.red_led_names:
            self.assertEqual(str(red_brightness), self._read(name, "brightness"))
            expected = "heartbeat" if red_brightness else "none"
            self.assertEqual(expected, self._read(name, "trigger"))

    def _portable_led_glob(self, pattern):
        if "*:green:brick-status" in pattern:
            names = self.green_led_names
        elif "*:red:brick-status" in pattern:
            names = self.red_led_names
        else:
            return []
        return [
            os.path.join(self.led_root, name, "trigger")
            for name in names
        ]

    def _read(self, led_name, file_name):
        path = os.path.join(self.led_root, led_name, file_name)
        with open(path, "r") as value_file:
            return value_file.read().strip()

    @staticmethod
    def _write(path, value):
        with open(path, "w") as value_file:
            value_file.write(value)


if __name__ == "__main__":
    unittest.main()
