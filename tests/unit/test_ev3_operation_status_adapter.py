#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the initial EV3 operation-status display."""

import os
import sys
import types
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from adapters.out_ev3_operation_status import Ev3OperationStatusAdapter


class RecordingImage(object):
    def __init__(self):
        self.paste_calls = []

    def paste(self, image, position):
        self.paste_calls.append((image, position))


class RecordingDraw(object):
    def __init__(self):
        self.text_calls = []

    def text(self, position, text, font=None, fill=None):
        self.text_calls.append((position, text, font, fill))


class RecordingDisplay(object):
    def __init__(self):
        self.image = RecordingImage()
        self.draw = RecordingDraw()
        self.update_calls = 0

    def update(self):
        self.update_calls += 1


class Ev3OperationStatusAdapterTests(unittest.TestCase):
    def test_general_status_background_is_packaged_as_valid_pbm(self):
        path = Ev3OperationStatusAdapter._asset_path()
        self.assertTrue(os.path.isfile(path), path)
        self.assertIn(os.path.join("assets", "screens", "cache"), path)
        background = Ev3OperationStatusAdapter._load_background()
        self.assertEqual((178, 128), background.size)
        self.assertEqual("1", background.mode)
        background.close()

    def test_reads_ev3_battery_by_explicit_power_supply_address(self):
        power_module = types.ModuleType("ev3dev2.power")
        supply = mock.Mock(measured_volts=7.2, max_volts=9.0)
        power_class = mock.Mock(return_value=supply)
        power_module.PowerSupply = power_class
        ev3dev2_module = types.ModuleType("ev3dev2")

        with mock.patch.dict(
                sys.modules,
                {"ev3dev2": ev3dev2_module, "ev3dev2.power": power_module}):
            value = Ev3OperationStatusAdapter._read_battery_percentage()

        self.assertEqual("80%", value)
        power_class.assert_called_once_with(address="legoev3-battery")

    def test_battery_reading_is_informational_when_device_is_unavailable(self):
        power_module = types.ModuleType("ev3dev2.power")
        power_module.PowerSupply = mock.Mock(side_effect=OSError("missing"))
        ev3dev2_module = types.ModuleType("ev3dev2")

        with mock.patch.dict(
                sys.modules,
                {"ev3dev2": ev3dev2_module, "ev3dev2.power": power_module}):
            value = Ev3OperationStatusAdapter._read_battery_percentage()

        self.assertEqual("Unavailable", value)

    def test_read_values_combines_battery_network_joystick_and_modes(self):
        mode_service = mock.Mock()
        mode_service.get_snapshot.return_value = {
            "command": "LOCAL",
            "control": "MANUAL"
        }
        adapter = Ev3OperationStatusAdapter(mode_service)

        with mock.patch.object(
                adapter, "_read_battery_percentage", return_value="92%"), \
                mock.patch.object(
                    adapter, "_read_ip_address", return_value="192.168.0.10"), \
                mock.patch.object(
                    adapter, "_read_joystick_status", return_value="Connected"):
            values = adapter._read_values()

        self.assertEqual(
            {
                "battery": "92%",
                "ip": "192.168.0.10",
                "joystick": "Connected",
                "command": "Local",
                "control": "Manual"
            },
            values
        )

    def test_remote_mode_displays_control_as_not_applicable(self):
        mode_service = mock.Mock()
        mode_service.get_snapshot.return_value = {
            "command": "REMOTE",
            "control": None
        }
        adapter = Ev3OperationStatusAdapter(mode_service)

        with mock.patch.object(
                adapter, "_read_battery_percentage", return_value="92%"), \
                mock.patch.object(
                    adapter, "_read_ip_address", return_value="192.168.0.10"), \
                mock.patch.object(
                    adapter, "_read_joystick_status", return_value="Connected"):
            values = adapter._read_values()

        self.assertEqual("Remote", values["command"])
        self.assertEqual("N/A", values["control"])

    def test_draw_places_all_five_status_values_and_updates_display(self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._font = object()
        adapter._compact_font = object()

        with mock.patch.object(
                adapter,
                "_read_values",
                return_value={
                    "battery": "100%",
                    "ip": "10.0.0.2",
                    "joystick": "Connected",
                    "command": "Local",
                    "control": "Manual"
                }):
            adapter._draw_current_screen()

        self.assertEqual(1, len(adapter._display.image.paste_calls))
        self.assertEqual(5, len(adapter._display.draw.text_calls))
        self.assertEqual(1, adapter._display.update_calls)

    def test_joystick_status_uses_configured_device_name(self):
        first = mock.Mock(name="first", spec=[])
        first.name = "Other Controller"
        first.close = mock.Mock()
        second = mock.Mock(name="second", spec=[])
        second.name = "Wireless Controller"
        second.close = mock.Mock()
        evdev_module = types.ModuleType("evdev")
        evdev_module.list_devices = mock.Mock(return_value=["/dev/a", "/dev/b"])
        evdev_module.InputDevice = mock.Mock(side_effect=[first, second])
        adapter = Ev3OperationStatusAdapter(
            joystick_device_name="Wireless Controller"
        )

        with mock.patch.dict(sys.modules, {"evdev": evdev_module}):
            status = adapter._read_joystick_status()

        self.assertEqual("Connected", status)
        first.close.assert_called_once_with()
        second.close.assert_called_once_with()

    def test_ready_prompt_speaks_rover_dr_online(self):
        sound = mock.Mock()
        sound_class = mock.Mock(return_value=sound)
        sound_class.PLAY_WAIT_FOR_COMPLETE = 0
        sound_module = types.ModuleType("ev3dev2.sound")
        sound_module.Sound = sound_class
        ev3dev2_module = types.ModuleType("ev3dev2")

        with mock.patch.dict(
                sys.modules,
                {"ev3dev2": ev3dev2_module, "ev3dev2.sound": sound_module}):
            Ev3OperationStatusAdapter._play_operator_prompt()

        sound.speak.assert_called_once_with(
            "Rover D R Online",
            espeak_opts="-a 200 -s 130 -ven-us",
            play_type=0
        )

    def test_close_stops_status_worker(self):
        adapter = Ev3OperationStatusAdapter()
        with mock.patch.object(adapter, "stop") as stop:
            adapter.close()
        stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()


def test_bluetooth_error_background_is_packaged_as_valid_pbm():
    path = Ev3OperationStatusAdapter._bluetooth_error_asset_path()
    assert os.path.isfile(path)
    background = Ev3OperationStatusAdapter._load_bluetooth_error_background()
    assert background.size == (178, 128)
    assert background.mode == "1"
    background.close()


def test_connection_error_switches_to_bluetooth_screen_and_retry_message():
    adapter = Ev3OperationStatusAdapter()
    adapter._display = RecordingDisplay()
    adapter._background = object()
    adapter._bluetooth_error_background = object()
    adapter._font = object()
    adapter._compact_font = object()

    adapter.show_joystick_connection_error(
        "Joystick unavailable. Automatic retry pending.", 3.0
    )

    assert adapter._bluetooth_error_active is True
    assert adapter._display.image.paste_calls[-1][0] is adapter._bluetooth_error_background
    texts = [call[1] for call in adapter._display.draw.text_calls]
    assert any("Joystick unavailable" in text for text in texts)
    assert "Retry: 3.0s" in texts


def test_connection_recovery_restores_general_status_screen():
    adapter = Ev3OperationStatusAdapter()
    adapter._display = RecordingDisplay()
    adapter._background = object()
    adapter._bluetooth_error_background = object()
    adapter._font = object()
    adapter._compact_font = object()
    adapter._bluetooth_error_active = True

    with mock.patch.object(adapter, "_read_values", return_value={
        "battery": "90%", "ip": "10.0.0.2", "joystick": "Connected",
        "command": "Local", "control": "Manual"
    }):
        adapter.show_joystick_connected("Wireless Controller")

    assert adapter._bluetooth_error_active is False
    assert adapter._display.image.paste_calls[-1][0] is adapter._background
