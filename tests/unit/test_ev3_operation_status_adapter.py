#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for EV3 ready, initialization and Bluetooth display states."""

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
        self.ellipse_calls = []
        self.polygon_calls = []

    @staticmethod
    def textbbox(position, text, font=None):
        del position
        del font
        return (0, 0, len(text) * 6, 10)

    def text(self, position, text, font=None, fill=None):
        self.text_calls.append((position, text, font, fill))

    def ellipse(self, bbox, fill=None):
        self.ellipse_calls.append((bbox, fill))

    def polygon(self, points, fill=None):
        self.polygon_calls.append((points, fill))


class RecordingDisplay(object):
    def __init__(self):
        self.image = RecordingImage()
        self.draw = RecordingDraw()
        self.update_calls = 0

    def update(self):
        self.update_calls += 1




class SequenceNavigationButtons(object):
    def __init__(self, left=None, right=None):
        self.left_values = list(left or [False])
        self.right_values = list(right or [False])

    @staticmethod
    def _next(values):
        if len(values) > 1:
            return values.pop(0)
        return values[0]

    @property
    def left(self):
        return self._next(self.left_values)

    @property
    def right(self):
        return self._next(self.right_values)




class FaultyLeftNavigationButtons(object):
    @property
    def left(self):
        raise OSError("temporary button read failure")

    @property
    def right(self):
        return True


class Ev3OperationStatusAdapterTestCase(unittest.TestCase):
    def test_startup_status_background_is_packaged_as_valid_pbm(self):
        path = os.path.join(
            os.path.dirname(Ev3OperationStatusAdapter._asset_path()),
            Ev3OperationStatusAdapter.STARTUP_BACKGROUND_FILENAME
        )

        self.assertEqual(
            "Screen 08 - Initialization Status.pbm",
            Ev3OperationStatusAdapter.STARTUP_BACKGROUND_FILENAME
        )
        self.assertTrue(os.path.isfile(path), path)
        background = Ev3OperationStatusAdapter._load_startup_background()
        self.assertEqual((178, 128), background.size)
        self.assertEqual("1", background.mode)
        background.close()

    def test_bluetooth_error_background_is_packaged_as_valid_pbm(self):
        path = os.path.join(
            os.path.dirname(Ev3OperationStatusAdapter._asset_path()),
            Ev3OperationStatusAdapter.BLUETOOTH_ERROR_FILENAME
        )

        self.assertTrue(os.path.isfile(path), path)
        background = (
            Ev3OperationStatusAdapter._load_bluetooth_error_background()
        )
        self.assertEqual((178, 128), background.size)
        self.assertEqual("1", background.mode)
        background.close()

    def test_connection_failure_shows_timestamped_error_and_restores_status(
            self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._startup_background = object()
        adapter._bluetooth_error_background = object()
        adapter._font = object()
        adapter._compact_font = object()
        adapter._bluetooth_message_font = object()
        adapter._bluetooth_timestamp_font = object()

        with mock.patch.object(
                adapter,
                "_current_timestamp",
                return_value="04/07/2026 15:30:45"), mock.patch.object(
                adapter,
                "_read_values",
                return_value={
                    "battery": "100%",
                    "ip": "192.168.1.2",
                    "joystick": "Connected",
                    "command": "Local",
                    "control": "Manual",
                    "front": "Nose",
                    "drive": "Differential"
                }):
            adapter.show_joystick_connection_error(
                "Joystick not found. Trying to connect.", 3.0
            )
            self.assertTrue(adapter._bluetooth_error_active)
            self.assertIs(
                adapter._bluetooth_error_background,
                adapter._display.image.paste_calls[-1][0]
            )
            rendered_text = [
                call[1] for call in adapter._display.draw.text_calls
            ]
            self.assertEqual(
                [
                    "Joystick",
                    "not found",
                    "Connecting...",
                    "04/07/2026 15:30:45"
                ],
                rendered_text
            )

            adapter.show_joystick_connected("Wireless Controller")
            self.assertFalse(adapter._bluetooth_error_active)
            self.assertIs(
                adapter._background,
                adapter._display.image.paste_calls[-1][0]
            )

    def test_bluetooth_error_reuses_token_buzzer_until_reconnected(self):
        adapter = Ev3OperationStatusAdapter()
        sound = mock.Mock()
        stop_event = mock.Mock()
        alert_thread = mock.Mock()

        with mock.patch(
            "adapters.out_ev3_operation_status."
            "Ev3OperatorAlertAdapter._try_start_alert",
            return_value=(sound, stop_event, alert_thread)
        ) as start_alert, mock.patch(
            "adapters.out_ev3_operation_status."
            "Ev3OperatorAlertAdapter._stop_alert"
        ) as stop_alert:
            adapter.show_joystick_connection_error(
                "Joystick not found. Trying to connect.", 3.0
            )
            adapter.show_joystick_connection_error(
                "Joystick still not found. Starting a new search.", 3.0
            )

            start_alert.assert_called_once_with()
            self.assertIs(sound, adapter._bluetooth_alert_sound)

            adapter.show_joystick_connected("Wireless Controller")

        stop_alert.assert_called_once_with(
            sound, stop_event, alert_thread
        )
        self.assertIsNone(adapter._bluetooth_alert_sound)
        self.assertIsNone(adapter._bluetooth_alert_stop_event)
        self.assertIsNone(adapter._bluetooth_alert_thread)

    def test_status_stop_also_stops_active_bluetooth_error_buzzer(self):
        adapter = Ev3OperationStatusAdapter()
        sound = mock.Mock()
        stop_event = mock.Mock()
        alert_thread = mock.Mock()
        adapter._bluetooth_alert_sound = sound
        adapter._bluetooth_alert_stop_event = stop_event
        adapter._bluetooth_alert_thread = alert_thread

        with mock.patch(
            "adapters.out_ev3_operation_status."
            "Ev3OperatorAlertAdapter._stop_alert"
        ) as stop_alert:
            adapter.stop()

        stop_alert.assert_called_once_with(
            sound, stop_event, alert_thread
        )

    def test_startup_gate_uses_bluetooth_artwork_while_joystick_is_missing(
            self):
        adapter = Ev3OperationStatusAdapter(startup_gated=True)
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._startup_background = object()
        adapter._bluetooth_error_background = object()
        adapter._font = object()
        adapter._compact_font = object()
        adapter._bluetooth_message_font = object()
        adapter._bluetooth_timestamp_font = object()

        with mock.patch.object(
                adapter,
                "_current_timestamp",
                return_value="05/07/2026 18:20:00"):
            adapter.show_joystick_connection_error(
                "Joystick not found. Trying to connect.", 3.0
            )

            self.assertFalse(adapter._startup_active)
            self.assertTrue(adapter._bluetooth_error_active)
            self.assertIs(
                adapter._bluetooth_error_background,
                adapter._display.image.paste_calls[-1][0]
            )
            rendered_text = [
                call[1] for call in adapter._display.draw.text_calls
            ]
            self.assertEqual(
                [
                    "Joystick",
                    "not found",
                    "Connecting...",
                    "05/07/2026 18:20:00"
                ],
                rendered_text
            )

    def test_startup_gate_uses_status_artwork_until_control_is_ready(self):
        adapter = Ev3OperationStatusAdapter(startup_gated=True)
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._startup_background = object()
        adapter._bluetooth_error_background = object()
        adapter._font = object()
        adapter._compact_font = object()
        adapter._bluetooth_message_font = object()
        adapter._bluetooth_timestamp_font = object()

        with mock.patch.object(
                adapter,
                "_current_timestamp",
                return_value="05/07/2026 18:30:00"), mock.patch.object(
                adapter,
                "_read_values",
                return_value={
                    "battery": "100%",
                    "ip": "192.168.1.2",
                    "joystick": "Connected",
                    "command": "Local",
                    "control": "Manual",
                    "front": "Nose",
                    "drive": "Differential"
                }), mock.patch.object(
                adapter, "_play_operator_prompt_async") as prompt:
            adapter.show_startup_progress(
                "Motor LLM connected in 1.234 s."
            )

            self.assertTrue(adapter._startup_active)
            self.assertIs(
                adapter._startup_background,
                adapter._display.image.paste_calls[-1][0]
            )
            rendered_text = [
                call[1] for call in adapter._display.draw.text_calls
            ]
            self.assertIn("Motor LLM connected", rendered_text)
            self.assertIn("in 1.234 s.", rendered_text)

            adapter.show_joystick_connected("Wireless Controller")

            self.assertFalse(adapter._startup_active)
            self.assertIs(
                adapter._background,
                adapter._display.image.paste_calls[-1][0]
            )
            prompt.assert_called_once_with()

    def test_startup_failure_preserves_four_explicit_operator_lines(self):
        adapter = Ev3OperationStatusAdapter(startup_gated=True)
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._startup_background = object()
        adapter._bluetooth_error_background = object()
        adapter._font = object()
        adapter._compact_font = object()
        adapter._bluetooth_message_font = object()
        adapter._bluetooth_timestamp_font = object()

        with mock.patch.object(
                adapter,
                "_current_timestamp",
                return_value="11/08/2026 15:06:13"):
            adapter.show_startup_progress(
                "Motor\ninitialization\nfailed. Retrying\nin 3.0 s."
            )

        rendered_text = [
            call[1] for call in adapter._display.draw.text_calls
        ]
        self.assertEqual(
            [
                "Motor",
                "initialization",
                "failed. Retrying",
                "in 3.0 s.",
                "11/08/2026 15:06:13"
            ],
            rendered_text
        )

    def test_startup_error_shows_screen_and_requests_buzzer(self):
        adapter = Ev3OperationStatusAdapter(startup_gated=True)
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._startup_background = object()
        adapter._bluetooth_error_background = object()
        adapter._font = object()
        adapter._compact_font = object()
        adapter._bluetooth_message_font = object()
        adapter._bluetooth_timestamp_font = object()

        with mock.patch.object(
                adapter, "_play_startup_error_tone_async") as buzzer:
            adapter.show_startup_error(
                "Motor\ninitialization\nfailed. Retrying\nin 3.0 s."
            )

        buzzer.assert_called_once_with()
        rendered_text = [
            call[1] for call in adapter._display.draw.text_calls
        ]
        self.assertEqual(
            [
                "Motor",
                "initialization",
                "failed. Retrying",
                "in 3.0 s.",
                adapter._startup_timestamp
            ],
            rendered_text
        )


    def test_startup_prompt_matches_front_drive_three_beep_cadence(self):
        sound = mock.Mock()
        sound_class = mock.Mock(return_value=sound)
        sound_class.PLAY_WAIT_FOR_COMPLETE = 0

        with mock.patch.dict(
                "sys.modules",
                {"ev3dev2.sound": mock.Mock(Sound=sound_class)}), \
                mock.patch(
                    "adapters.out_ev3_operation_status.time.sleep"
                ) as sleep_mock:
            Ev3OperationStatusAdapter._play_startup_prompt()

        self.assertEqual(3, sound.tone.call_count)
        sound.tone.assert_has_calls([
            mock.call(1000, 70, play_type=0),
            mock.call(1000, 70, play_type=0),
            mock.call(1000, 70, play_type=0)
        ])
        self.assertEqual([mock.call(0.04), mock.call(0.04)], sleep_mock.call_args_list)

    def test_startup_screen_is_drawn_before_prompt_and_deferred_loading(self):
        adapter = Ev3OperationStatusAdapter(startup_gated=True)
        events = []
        thread = mock.Mock()
        thread.is_alive.return_value = False

        with mock.patch(
                "adapters.out_ev3_operation_status.create_ev3_display",
                return_value=RecordingDisplay()), mock.patch.object(
                adapter, "_load_initial_screen_resources",
                side_effect=lambda: events.append("initial_resources")), \
                mock.patch.object(
                    adapter, "_create_buttons", return_value=None), \
                mock.patch.object(
                    adapter, "_draw_current_screen",
                    side_effect=lambda: events.append("draw")), \
                mock.patch.object(
                    adapter, "_play_startup_prompt",
                    side_effect=lambda: events.append("prompt")), \
                mock.patch.object(
                    adapter, "_load_deferred_screen_resources",
                    side_effect=lambda: events.append("deferred_resources")), \
                mock.patch(
                    "adapters.out_ev3_operation_status.threading.Thread",
                    return_value=thread):
            adapter.start()

        self.assertEqual(
            ["initial_resources", "draw", "prompt", "deferred_resources"],
            events
        )

    def test_startup_error_buzzer_plays_descending_two_tone_signal(self):
        sound = mock.Mock()
        sound_class = mock.Mock(return_value=sound)
        sound_class.PLAY_WAIT_FOR_COMPLETE = 0

        with mock.patch.dict(
                "sys.modules",
                {"ev3dev2.sound": mock.Mock(Sound=sound_class)}):
            Ev3OperationStatusAdapter._play_startup_error_tone()

        self.assertEqual(2, sound.tone.call_count)
        sound.tone.assert_has_calls([
            mock.call(220, 180, play_type=0),
            mock.call(130, 280, play_type=0)
        ])

    def test_ready_prompt_speaks_rover_dr_online(self):
        sound = mock.Mock()
        sound_class = mock.Mock(return_value=sound)
        sound_class.PLAY_WAIT_FOR_COMPLETE = 0

        with mock.patch.dict(
                "sys.modules",
                {"ev3dev2.sound": mock.Mock(Sound=sound_class)}):
            Ev3OperationStatusAdapter._play_operator_prompt()

        sound.speak.assert_called_once_with(
            "Rover D R Online",
            espeak_opts="-a 200 -s 130 -ven-us",
            play_type=0
        )
        sound.tone.assert_not_called()

    def test_ready_announcement_is_not_repeated_after_reconnection(self):
        adapter = Ev3OperationStatusAdapter(startup_gated=True)
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._startup_background = object()
        adapter._bluetooth_error_background = object()
        adapter._font = object()
        adapter._compact_font = object()
        adapter._bluetooth_message_font = object()
        adapter._bluetooth_timestamp_font = object()

        with mock.patch.object(
                adapter,
                "_read_values",
                return_value={
                    "battery": "100%",
                    "ip": "192.168.1.2",
                    "joystick": "Connected",
                    "command": "Local",
                    "control": "Manual",
                    "front": "Nose",
                    "drive": "Differential"
                }), mock.patch.object(
                adapter, "_play_operator_prompt_async") as prompt:
            adapter.show_joystick_connected("Wireless Controller")
            adapter.show_joystick_connection_error(
                "Joystick Bluetooth connection lost.", 3.0
            )
            adapter.show_joystick_connected("Wireless Controller")

        prompt.assert_called_once_with()

    def test_retry_message_reports_still_missing_and_three_second_search(self):
        self.assertEqual(
            ("Still not found", "New search", "in 3s"),
            Ev3OperationStatusAdapter._bluetooth_message_lines(
                "Joystick still not found. Starting a new search.", 3.0
            )
        )

    def test_disconnect_message_reports_new_search(self):
        self.assertEqual(
            ("Connection lost", "New search", "in 3s"),
            Ev3OperationStatusAdapter._bluetooth_message_lines(
                "Joystick Bluetooth connection lost. Starting a new search.",
                3.0
            )
        )

    def test_general_status_reads_selected_drive_mode(self):
        adapter = Ev3OperationStatusAdapter(operation_mode_service={
            "command": "LOCAL",
            "control": "MANUAL",
            "front": "NOSE",
            "drive": "DIFFERENTIAL",
            "centric": None
        })

        with mock.patch.object(
                adapter, "_read_ip_address", return_value="192.168.1.2"), \
                mock.patch.object(
                    adapter, "_read_joystick_status",
                    return_value="Connected"), \
                mock.patch.object(
                    adapter, "_read_battery_percentage",
                    return_value="100%"):
            values = adapter._read_values()

        self.assertEqual("Dif. R-Bogie", values["drive"])

    def test_general_status_displays_r_bogie_differential_mode(self):
        adapter = Ev3OperationStatusAdapter(operation_mode_service={
            "command": "LOCAL",
            "control": "MANUAL",
            "front": "NOSE",
            "drive": "DIFFERENTIAL",
            "centric": None,
            "differential_mode": "R-BOGIE"
        })

        with mock.patch.object(
                adapter, "_read_ip_address", return_value="192.168.1.2"):
            values = adapter._read_values()

        self.assertEqual("Dif. R-Bogie", values["drive"])

    def test_general_status_reads_mecanum_drive_mode(self):
        adapter = Ev3OperationStatusAdapter(operation_mode_service={
            "command": "LOCAL",
            "control": "MANUAL",
            "front": "NOSE",
            "drive": "MECANUM",
            "centric": "CHASSIS"
        })

        with mock.patch.object(
                adapter, "_read_ip_address", return_value="192.168.1.2"), \
                mock.patch.object(
                    adapter, "_read_joystick_status",
                    return_value="Connected"), \
                mock.patch.object(
                    adapter, "_read_battery_percentage",
                    return_value="100%"):
            values = adapter._read_values()

        self.assertEqual("Mec. Chassis", values["drive"])

    def test_general_status_combines_mecanum_field_mode(self):
        adapter = Ev3OperationStatusAdapter(operation_mode_service={
            "command": "LOCAL",
            "control": "MANUAL",
            "front": "TAIL",
            "drive": "MECANUM",
            "centric": "FIELD"
        })

        with mock.patch.object(
                adapter, "_read_ip_address", return_value="192.168.1.2"):
            values = adapter._read_values()

        self.assertEqual("Tail", values["front"])
        self.assertEqual("Mec. Field", values["drive"])

    def test_battery_measurements_keep_volts_and_convert_amps_to_milliamps(self):
        class FakeDeviceNotFound(Exception):
            pass

        class FakePowerSupply(object):
            def __init__(self, address=None):
                self.address = address
                self.measured_volts = 7.45
                self.measured_amps = 0.3204

        ev3dev2_module = types.ModuleType("ev3dev2")
        ev3dev2_module.DeviceNotFound = FakeDeviceNotFound
        power_module = types.ModuleType("ev3dev2.power")
        power_module.PowerSupply = FakePowerSupply

        with mock.patch.dict(
                sys.modules,
                {"ev3dev2": ev3dev2_module, "ev3dev2.power": power_module}):
            voltage, current = (
                Ev3OperationStatusAdapter._read_battery_measurements()
            )

        self.assertEqual("7.45 V", voltage)
        self.assertEqual("320 mA", current)

    def test_general_status_renders_primary_values_and_battery(self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._font = object()

        with mock.patch.object(
                adapter,
                "_read_values",
                return_value={
                    "ip": "192.168.1.2",
                    "command": "Local",
                    "control": "Manual",
                    "front": "Nose",
                    "drive": "Mec. Field",
                    "battery_voltage": "7.45 V",
                    "battery_current": "320 mA"
                }):
            adapter._draw_status_locked()

        self.assertEqual(
            [
                ((52, 46), "192.168.1.2"),
                ((52, 58), "Local"),
                ((52, 70), "Manual"),
                ((52, 82), "Nose"),
                ((52, 94), "Mec. Field"),
                ((133, 58), "Bat."),
                ((125, 71), "7.45 V"),
                ((125, 83), "320 mA")
            ],
            [
                (call[0], call[1])
                for call in adapter._display.draw.text_calls
            ]
        )
        self.assertEqual(
            [
                ((44, 50, 47, 53), 0),
                ((44, 62, 47, 65), 0),
                ((44, 74, 47, 77), 0),
                ((44, 86, 47, 89), 0),
                ((44, 98, 47, 101), 0),
                ((125, 61, 128, 64), 0)
            ],
            adapter._display.draw.ellipse_calls
        )
        self.assertTrue(all(
            call[2] is adapter._font
            for call in adapter._display.draw.text_calls
        ))


    def test_motor_status_backgrounds_are_packaged_as_valid_pbm(self):
        for screen_name, filename in (
                (Ev3OperationStatusAdapter.SCREEN_LARGE_MOTORS,
                 "Screen 06 - Large Motors Status.pbm"),
                (Ev3OperationStatusAdapter.SCREEN_MEDIUM_MOTORS,
                 "Screen 07 - Medium Motors Status.pbm")):
            self.assertEqual(
                filename,
                Ev3OperationStatusAdapter.BACKGROUND_FILENAMES[screen_name]
            )
            background = Ev3OperationStatusAdapter._load_background(screen_name)
            self.assertEqual((178, 128), background.size)
            self.assertEqual("1", background.mode)
            background.close()

    def test_navigation_tolerates_transient_button_read_error(self):
        self.assertEqual(
            "right",
            Ev3OperationStatusAdapter._pressed_navigation_button(
                FaultyLeftNavigationButtons()
            )
        )

    def test_status_navigation_uses_faster_button_polling(self):
        self.assertEqual(0.02, Ev3OperationStatusAdapter.BUTTON_POLL_SECONDS)

    def test_navigation_changes_screen_on_press_edge_without_telemetry_wait(self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        general_background = object()
        large_background = object()
        adapter._status_backgrounds = {
            adapter.SCREEN_GENERAL: general_background,
            adapter.SCREEN_LARGE_MOTORS: large_background
        }
        adapter._background = general_background
        adapter._buttons = SequenceNavigationButtons(right=[True])

        with mock.patch.object(
                adapter, "_read_motor_status_values") as read_motor:
            with mock.patch(
                    "adapters.out_ev3_operation_status.Ev3ButtonFeedback.play"
            ) as feedback:
                changed = adapter._poll_status_navigation()

        self.assertTrue(changed)
        feedback.assert_called_once_with()
        self.assertEqual(adapter.SCREEN_LARGE_MOTORS, adapter._status_screen)
        self.assertIs(
            large_background,
            adapter._display.image.paste_calls[-1][0]
        )
        self.assertEqual(1, adapter._display.update_calls)
        read_motor.assert_not_called()
        self.assertTrue(adapter._refresh_event.is_set())

    def test_held_navigation_button_changes_only_once_until_release(self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        adapter._status_backgrounds = {
            adapter.SCREEN_GENERAL: object(),
            adapter.SCREEN_LARGE_MOTORS: object(),
            adapter.SCREEN_MEDIUM_MOTORS: object()
        }
        adapter._background = adapter._status_backgrounds[adapter.SCREEN_GENERAL]
        adapter._buttons = SequenceNavigationButtons(
            right=[True, True, False, True]
        )

        self.assertTrue(adapter._poll_status_navigation())
        self.assertEqual(adapter.SCREEN_LARGE_MOTORS, adapter._status_screen)
        self.assertFalse(adapter._poll_status_navigation())
        self.assertEqual(adapter.SCREEN_LARGE_MOTORS, adapter._status_screen)
        self.assertFalse(adapter._poll_status_navigation())
        self.assertTrue(adapter._poll_status_navigation())
        self.assertEqual(adapter.SCREEN_MEDIUM_MOTORS, adapter._status_screen)

    def test_status_navigation_beeps_only_on_a_new_press_edge(self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        adapter._status_backgrounds = {
            adapter.SCREEN_GENERAL: object(),
            adapter.SCREEN_LARGE_MOTORS: object(),
            adapter.SCREEN_MEDIUM_MOTORS: object()
        }
        adapter._background = adapter._status_backgrounds[adapter.SCREEN_GENERAL]
        adapter._buttons = SequenceNavigationButtons(
            right=[True, True, False, True]
        )

        with mock.patch(
                "adapters.out_ev3_operation_status.Ev3ButtonFeedback.play"
        ) as feedback:
            self.assertTrue(adapter._poll_status_navigation())
            self.assertFalse(adapter._poll_status_navigation())
            self.assertFalse(adapter._poll_status_navigation())
            self.assertTrue(adapter._poll_status_navigation())

        self.assertEqual(2, feedback.call_count)

    def test_right_button_cycles_general_large_medium_general(self):
        adjacent = Ev3OperationStatusAdapter._adjacent_status_screen
        general = Ev3OperationStatusAdapter.SCREEN_GENERAL
        large = Ev3OperationStatusAdapter.SCREEN_LARGE_MOTORS
        medium = Ev3OperationStatusAdapter.SCREEN_MEDIUM_MOTORS

        self.assertEqual(large, adjacent(general, "right"))
        self.assertEqual(medium, adjacent(large, "right"))
        self.assertEqual(general, adjacent(medium, "right"))

    def test_left_button_cycles_general_medium_large_general(self):
        adjacent = Ev3OperationStatusAdapter._adjacent_status_screen
        general = Ev3OperationStatusAdapter.SCREEN_GENERAL
        large = Ev3OperationStatusAdapter.SCREEN_LARGE_MOTORS
        medium = Ev3OperationStatusAdapter.SCREEN_MEDIUM_MOTORS

        self.assertEqual(medium, adjacent(general, "left"))
        self.assertEqual(large, adjacent(medium, "left"))
        self.assertEqual(general, adjacent(large, "left"))


    def test_general_status_draws_cursor_on_bottom_buttons_row(self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._status_backgrounds = {
            adapter.SCREEN_GENERAL: adapter._background
        }
        adapter._font = object()

        with mock.patch.object(
                adapter,
                "_read_values",
                return_value={
                    "ip": "192.168.1.2",
                    "command": "Local",
                    "control": "Manual",
                    "front": "Nose",
                    "drive": "Mec. Field"
                }):
            adapter._draw_general_status_locked()

        self.assertIn(
            (
                ((5, 113), (5, 121), (13, 117)),
                0
            ),
            adapter._display.draw.polygon_calls
        )

    def test_motor_status_draws_cursor_on_bottom_buttons_row(self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._status_backgrounds = {
            adapter.SCREEN_LARGE_MOTORS: adapter._background
        }
        adapter._motor_font = object()

        with mock.patch.object(
                adapter,
                "_read_motor_status_values",
                return_value={
                    "left": {
                        "speed": "+480 °/s",
                        "duty_cycle": "+62 %",
                        "position": "+1024 °",
                        "state": "running"
                    },
                    "right": {
                        "speed": "+475 °/s",
                        "duty_cycle": "+60 %",
                        "position": "+998 °",
                        "state": "running"
                    }
                }):
            adapter._draw_motor_status_locked(adapter.SCREEN_LARGE_MOTORS)

        self.assertIn(
            (
                ((5, 113), (5, 121), (13, 117)),
                0
            ),
            adapter._display.draw.polygon_calls
        )

    def test_motor_status_renders_requested_three_columns_on_general_rows(self):
        adapter = Ev3OperationStatusAdapter()
        adapter._display = RecordingDisplay()
        adapter._background = object()
        adapter._status_backgrounds = {
            adapter.SCREEN_LARGE_MOTORS: object()
        }
        adapter._motor_font = object()

        with mock.patch.object(
                adapter,
                "_read_motor_status_values",
                return_value={
                    "left": {
                        "speed": "480",
                        "duty_cycle": "62",
                        "position": "1024",
                        "state": "running"
                    },
                    "right": {
                        "speed": "475",
                        "duty_cycle": "60",
                        "position": "998",
                        "state": "running"
                    }
                }):
            adapter._draw_motor_status_locked(adapter.SCREEN_LARGE_MOTORS)

        rendered = [
            (call[0], call[1])
            for call in adapter._display.draw.text_calls
        ]
        self.assertIn(
            ((adapter.MOTOR_LABEL_RIGHT - 30, 58), "Speed"), rendered
        )
        self.assertIn(
            ((adapter.MOTOR_LABEL_RIGHT - 30, 70), "Cycle"), rendered
        )
        self.assertIn(
            ((adapter.MOTOR_LABEL_RIGHT - 24, 82), "Pos."), rendered
        )
        self.assertIn(
            ((adapter.MOTOR_LABEL_RIGHT - 30, 94), "State"), rendered
        )
        self.assertTrue(any(
            position[1] == 46 and text == "Left"
            for position, text in rendered
        ))
        self.assertTrue(any(
            position[1] == 46 and text == "Right"
            for position, text in rendered
        ))

    def test_motor_dynamic_values_prefer_physical_telemetry(self):
        values = Ev3OperationStatusAdapter._motor_dynamic_values({
            "speed": 321,
            "speed_sp": 600,
            "duty_cycle": 44,
            "duty_cycle_sp": 80,
            "position": 1024,
            "state": ["running"],
            "motion_state": "STOPPED"
        })

        self.assertEqual("+321 °/s", values["speed"])
        self.assertEqual("+44 %", values["duty_cycle"])
        self.assertEqual("+1024 °", values["position"])
        self.assertEqual("running", values["state"])


    def test_motor_dynamic_values_include_sign_and_engineering_units(self):
        values = Ev3OperationStatusAdapter._motor_dynamic_values({
            "speed": -420,
            "duty_cycle": 65,
            "position": 1350,
            "state": ["running"]
        })

        self.assertEqual("-420 °/s", values["speed"])
        self.assertEqual("+65 %", values["duty_cycle"])
        self.assertEqual("+1350 °", values["position"])
        self.assertEqual("running", values["state"])

    def test_empty_ev3_motor_state_is_rendered_as_stopped(self):
        values = Ev3OperationStatusAdapter._motor_dynamic_values({
            "speed": 0,
            "duty_cycle": 0,
            "position": 0,
            "state": []
        })

        self.assertEqual("+0 °/s", values["speed"])
        self.assertEqual("+0 %", values["duty_cycle"])
        self.assertEqual("+0 °", values["position"])
        self.assertEqual("stopped", values["state"])

    def test_empty_ev3_state_uses_motion_state_fallback(self):
        values = Ev3OperationStatusAdapter._motor_dynamic_values({
            "state": [],
            "motion_state": "STOPPED"
        })

        self.assertEqual("stopped", values["state"])

    def test_bluetooth_fonts_use_compact_status_screen_sizes(self):
        self.assertEqual(12, Ev3OperationStatusAdapter.BLUETOOTH_MESSAGE_FONT_SIZE)
        self.assertEqual(11, Ev3OperationStatusAdapter.BLUETOOTH_TIMESTAMP_FONT_SIZE)


if __name__ == "__main__":
    unittest.main()
