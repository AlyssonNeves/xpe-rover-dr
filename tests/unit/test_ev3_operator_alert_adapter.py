#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the EV3 operator alert output adapter."""

import sys
import types
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from adapters.out_ev3_operator_alert import Ev3OperatorAlertAdapter
from infrastructure.ev3.screen_image import EV3_SCREEN_SIZE


class Ev3OperatorAlertAdapterTestCase(unittest.TestCase):
    """Covers EV3 screen, LED, sound and button integration."""

    def test_alert_uses_deeper_frequency(self):
        self.assertEqual(130, Ev3OperatorAlertAdapter.ALERT_FREQUENCY_HZ)

    def test_alert_cycle_matches_low_load_heartbeat_period(self):
        self.assertEqual(385, Ev3OperatorAlertAdapter.ALERT_TONE_MS)
        self.assertEqual(400, Ev3OperatorAlertAdapter.ALERT_PAUSE_MS)
        self.assertAlmostEqual(0.785, Ev3OperatorAlertAdapter.ALERT_CYCLE_SECONDS)

    def test_initialization_error_background_asset_exists(self):
        path = Ev3OperatorAlertAdapter._asset_path()

        self.assertTrue(
            path.endswith(Ev3OperatorAlertAdapter.BACKGROUND_FILENAME)
        )
        with open(path, "rb") as image_file:
            self.assertEqual(b"P4", image_file.read(2))

    def test_initialization_error_background_matches_ev3_display(self):
        background = Ev3OperatorAlertAdapter._load_background()

        self.assertEqual(EV3_SCREEN_SIZE, background.size)
        self.assertEqual("1", background.mode)

    def test_token_error_screen_uses_one_dynamic_background_and_original_fonts(self):
        display = mock.Mock()
        background = mock.Mock()
        font = mock.Mock()
        lines = [
            "Missing tokens:", "SHUTDOWN", "HARDWARE API",
            "Press any button to finish"
        ]

        with mock.patch.object(
            Ev3OperatorAlertAdapter,
            "_load_background",
            return_value=background
        ) as load_background, mock.patch.object(
            Ev3OperatorAlertAdapter,
            "_load_font",
            return_value=font
        ) as load_font, mock.patch.object(
            Ev3OperatorAlertAdapter,
            "_draw_centered_text"
        ) as draw_text:
            Ev3OperatorAlertAdapter._draw_error_screen(display, lines)

        load_background.assert_called_once_with()
        self.assertEqual(
            [
                mock.call(Ev3OperatorAlertAdapter.MAIN_TEXT_FONT_SIZE),
                mock.call(Ev3OperatorAlertAdapter.FOOTER_TEXT_FONT_SIZE)
            ],
            load_font.call_args_list
        )
        display.image.paste.assert_called_once_with(background, (0, 0))
        self.assertEqual(4, draw_text.call_count)
        display.update.assert_called_once_with()

    def test_original_truetype_font_is_cached_after_first_load(self):
        Ev3OperatorAlertAdapter._FONT_CACHE = {}
        Ev3OperatorAlertAdapter._FONT_PATH = None
        font = mock.Mock()

        with mock.patch(
            "PIL.ImageFont.truetype", return_value=font
        ) as truetype, mock.patch(
            "PIL.ImageFont.load_default"
        ) as load_default:
            first = Ev3OperatorAlertAdapter._load_font(12)
            second = Ev3OperatorAlertAdapter._load_font(12)

        self.assertIs(font, first)
        self.assertIs(font, second)
        truetype.assert_called_once_with(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
            12
        )
        load_default.assert_not_called()
        Ev3OperatorAlertAdapter._FONT_CACHE = {}
        Ev3OperatorAlertAdapter._FONT_PATH = None

    def test_prepare_render_resources_warms_background_and_both_fonts(self):
        background = mock.Mock()

        with mock.patch.object(
            Ev3OperatorAlertAdapter,
            "_load_background",
            return_value=background
        ) as load_background, mock.patch.object(
            Ev3OperatorAlertAdapter, "_load_font"
        ) as load_font:
            Ev3OperatorAlertAdapter.prepare_render_resources()

        load_background.assert_called_once_with()
        background.close.assert_called_once_with()
        self.assertEqual(
            [
                mock.call(Ev3OperatorAlertAdapter.MAIN_TEXT_FONT_SIZE),
                mock.call(Ev3OperatorAlertAdapter.FOOTER_TEXT_FONT_SIZE)
            ],
            load_font.call_args_list
        )

    def test_button_pressed_accepts_any_button_without_event_processing(self):
        buttons = mock.Mock()
        buttons.any.return_value = True
        self.assertTrue(Ev3OperatorAlertAdapter._button_pressed(buttons))
        buttons.any.assert_called_once_with()
        buttons.process.assert_not_called()

    def test_button_pressed_falls_back_to_named_properties(self):
        buttons = mock.Mock()
        buttons.any.side_effect = AttributeError()
        buttons.up = False
        buttons.down = False
        buttons.left = False
        buttons.right = True
        buttons.enter = False
        buttons.backspace = False
        self.assertTrue(Ev3OperatorAlertAdapter._button_pressed(buttons))

    def test_start_alert_creates_and_starts_daemon_thread(self):
        sound = mock.Mock()
        stop_event = mock.Mock()
        alert_thread = mock.Mock()

        with mock.patch(
            "adapters.out_ev3_operator_alert.Event",
            return_value=stop_event
        ), mock.patch(
            "adapters.out_ev3_operator_alert.Thread",
            return_value=alert_thread
        ) as thread_class:
            result = Ev3OperatorAlertAdapter._start_alert(sound)

        self.assertEqual((stop_event, alert_thread), result)
        thread_class.assert_called_once_with(
            target=Ev3OperatorAlertAdapter._run_startup_alert,
            args=(sound, stop_event)
        )
        self.assertTrue(alert_thread.daemon)
        alert_thread.start.assert_called_once_with()

    def test_run_alert_phase_uses_non_blocking_tone(self):
        sound = mock.Mock()
        sound_process = mock.Mock()
        sound.tone.return_value = sound_process
        stop_event = mock.Mock()
        stop_event.wait.return_value = False
        sound_class = mock.Mock()
        sound_class.PLAY_NO_WAIT_FOR_COMPLETE = 1
        sound_module = types.ModuleType("ev3dev2.sound")
        sound_module.Sound = sound_class
        ev3dev2_module = types.ModuleType("ev3dev2")

        with mock.patch.dict(
            sys.modules,
            {
                "ev3dev2": ev3dev2_module,
                "ev3dev2.sound": sound_module
            }
        ):
            stopped = Ev3OperatorAlertAdapter._run_alert_phase(
                sound,
                stop_event
            )

        self.assertFalse(stopped)
        sound.tone.assert_called_once_with(
            Ev3OperatorAlertAdapter.ALERT_FREQUENCY_HZ,
            Ev3OperatorAlertAdapter.ALERT_TONE_MS,
            play_type=1
        )
        stop_event.wait.assert_called_once_with(
            Ev3OperatorAlertAdapter.ALERT_CYCLE_SECONDS
        )

    def test_show_waits_for_button_with_synchronized_alert(self):
        display = mock.Mock()
        display_module = types.ModuleType("ev3dev2.display")
        display_module.Display = mock.Mock(return_value=display)
        buttons = mock.Mock()
        button_module = types.ModuleType("ev3dev2.button")
        button_module.Button = mock.Mock(return_value=buttons)
        sound = mock.Mock()
        sound_module = types.ModuleType("ev3dev2.sound")
        sound_module.Sound = mock.Mock(return_value=sound)
        ev3dev2_module = types.ModuleType("ev3dev2")
        stop_event = mock.Mock()
        alert_thread = mock.Mock()
        adapter = Ev3OperatorAlertAdapter()
        lines = ["ROVER DR", "STARTUP ERROR", "Missing config:"]

        with mock.patch.dict(
            sys.modules,
            {
                "ev3dev2": ev3dev2_module,
                "ev3dev2.button": button_module,
                "ev3dev2.display": display_module,
                "ev3dev2.sound": sound_module
            }
        ), mock.patch.object(
            adapter, "_draw_error_screen"
        ) as draw_error_screen, mock.patch.object(
            adapter, "_button_pressed", side_effect=[False, False, True]
        ), mock.patch.object(
            adapter,
            "_try_start_alert",
            return_value=(sound, stop_event, alert_thread)
        ) as start_alert, mock.patch.object(
            adapter, "_stop_alert"
        ) as stop_alert, mock.patch(
            "adapters.out_ev3_operator_alert.Ev3ButtonFeedback.play"
        ) as play_beep, mock.patch(
            "adapters.out_ev3_operator_alert.time.sleep"
        ), mock.patch(
            "adapters.out_ev3_operator_alert.sys.stdout.flush"
        ):
            shown = adapter.show_fatal_error(lines)

        self.assertTrue(shown)
        draw_error_screen.assert_called_once_with(display, lines)
        start_alert.assert_called_once_with()
        stop_alert.assert_called_once_with(
            sound,
            stop_event,
            alert_thread
        )
        play_beep.assert_called_once_with(sound)

    def test_show_displays_screen_before_buzzer_and_fault_led(self):
        status_led = mock.Mock()
        adapter = Ev3OperatorAlertAdapter(status_led_port=status_led)
        display = mock.Mock()
        buttons = mock.Mock()
        sound = mock.Mock()
        stop_event = mock.Mock()
        alert_thread = mock.Mock()
        sequence = []

        button_module = types.ModuleType("ev3dev2.button")
        button_module.Button = mock.Mock(return_value=buttons)
        ev3dev2_module = types.ModuleType("ev3dev2")

        def create_display():
            sequence.append("display")
            return display

        def draw_screen(active_display, lines):
            self.assertIs(display, active_display)
            self.assertEqual(["configuration error"], lines)
            sequence.append("screen")

        def start_alert():
            sequence.append("buzzer")
            return sound, stop_event, alert_thread

        status_led.set_fault.side_effect = lambda *args: sequence.append("led")

        with mock.patch.dict(
            sys.modules,
            {
                "ev3dev2": ev3dev2_module,
                "ev3dev2.button": button_module
            }
        ), mock.patch(
            "adapters.out_ev3_operator_alert.create_ev3_display",
            side_effect=create_display
        ), mock.patch.object(
            adapter, "_draw_error_screen", side_effect=draw_screen
        ), mock.patch.object(
            adapter, "_try_start_alert", side_effect=start_alert
        ), mock.patch.object(
            adapter, "_button_pressed", side_effect=[False, True]
        ), mock.patch.object(
            adapter, "_stop_alert"
        ), mock.patch(
            "adapters.out_ev3_operator_alert.Ev3ButtonFeedback.play"
        ), mock.patch(
            "adapters.out_ev3_operator_alert.time.sleep"
        ), mock.patch(
            "adapters.out_ev3_operator_alert.sys.stdout.flush"
        ):
            shown = adapter.show_fatal_error(["configuration error"])

        self.assertTrue(shown)
        self.assertEqual(["display", "screen", "buzzer", "led"], sequence)
        status_led.set_fault.assert_called_once_with("configuration", True)

    def test_status_led_factory_is_not_called_until_after_screen_and_buzzer(self):
        status_led = mock.Mock()
        sequence = []

        def status_led_factory():
            sequence.append("led-factory")
            return status_led

        adapter = Ev3OperatorAlertAdapter(
            status_led_factory=status_led_factory
        )
        display = mock.Mock()
        buttons = mock.Mock()
        sound = mock.Mock()
        stop_event = mock.Mock()
        alert_thread = mock.Mock()
        button_module = types.ModuleType("ev3dev2.button")
        button_module.Button = mock.Mock(return_value=buttons)
        ev3dev2_module = types.ModuleType("ev3dev2")

        with mock.patch.dict(
            sys.modules,
            {"ev3dev2": ev3dev2_module, "ev3dev2.button": button_module}
        ), mock.patch(
            "adapters.out_ev3_operator_alert.create_ev3_display",
            side_effect=lambda: sequence.append("display") or display
        ), mock.patch.object(
            adapter, "_draw_error_screen",
            side_effect=lambda *args: sequence.append("screen")
        ), mock.patch.object(
            adapter, "_try_start_alert",
            side_effect=lambda: sequence.append("buzzer") or (
                sound, stop_event, alert_thread
            )
        ), mock.patch.object(
            adapter, "_button_pressed", side_effect=[False, True]
        ), mock.patch.object(
            adapter, "_stop_alert"
        ), mock.patch(
            "adapters.out_ev3_operator_alert.Ev3ButtonFeedback.play"
        ), mock.patch(
            "adapters.out_ev3_operator_alert.time.sleep"
        ), mock.patch(
            "adapters.out_ev3_operator_alert.sys.stdout.flush"
        ):
            shown = adapter.show_fatal_error(["configuration error"])

        self.assertTrue(shown)
        self.assertEqual(
            ["display", "screen", "buzzer", "led-factory"], sequence
        )
        status_led.set_fault.assert_called_once_with("configuration", True)

    def test_run_startup_alert_safely_stops_when_sound_is_unavailable(self):
        sound = mock.Mock()
        stop_event = mock.Mock()
        stop_event.is_set.return_value = False

        with mock.patch.object(
            Ev3OperatorAlertAdapter,
            "_run_alert_phase",
            side_effect=ImportError()
        ):
            result = Ev3OperatorAlertAdapter._run_startup_alert(
                sound,
                stop_event
            )

        self.assertIsNone(result)

    def test_show_falls_back_when_ev3_console_is_unavailable(self):
        adapter = Ev3OperatorAlertAdapter()
        with mock.patch.dict(sys.modules, {"ev3dev2": None}):
            self.assertFalse(
                adapter.show_fatal_error(["configuration error"])
            )


if __name__ == "__main__":
    unittest.main()
