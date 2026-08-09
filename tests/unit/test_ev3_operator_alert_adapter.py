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


class Ev3OperatorAlertAdapterTestCase(unittest.TestCase):
    """Covers EV3 screen, LED, sound and button integration."""

    def test_alert_uses_deeper_frequency(self):
        self.assertEqual(130, Ev3OperatorAlertAdapter.ALERT_FREQUENCY_HZ)

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
        leds = mock.Mock()
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
            result = Ev3OperatorAlertAdapter._start_alert(leds, sound)

        self.assertEqual((stop_event, alert_thread), result)
        thread_class.assert_called_once_with(
            target=Ev3OperatorAlertAdapter._run_startup_alert,
            args=(leds, sound, stop_event)
        )
        self.assertTrue(alert_thread.daemon)
        alert_thread.start.assert_called_once_with()

    def test_run_alert_phase_uses_non_blocking_tone_and_led_colors(self):
        leds = mock.Mock()
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
                leds,
                sound,
                stop_event,
                "RED",
                "BLACK"
            )

        self.assertFalse(stopped)
        self.assertEqual(
            [mock.call("LEFT", "RED"), mock.call("RIGHT", "BLACK")],
            leds.set_color.call_args_list
        )
        sound.tone.assert_called_once_with(
            Ev3OperatorAlertAdapter.ALERT_FREQUENCY_HZ,
            Ev3OperatorAlertAdapter.ALERT_TONE_MS,
            play_type=1
        )
        stop_event.wait.assert_called_once_with(
            Ev3OperatorAlertAdapter.ALERT_CYCLE_SECONDS
        )

    def test_show_waits_for_button_with_synchronized_alert(self):
        console = mock.Mock()
        console_module = types.ModuleType("ev3dev2.console")
        console_module.Console = mock.Mock(return_value=console)
        buttons = mock.Mock()
        button_module = types.ModuleType("ev3dev2.button")
        button_module.Button = mock.Mock(return_value=buttons)
        leds = mock.Mock()
        leds_module = types.ModuleType("ev3dev2.led")
        leds_module.Leds = mock.Mock(return_value=leds)
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
                "ev3dev2.console": console_module,
                "ev3dev2.led": leds_module,
                "ev3dev2.sound": sound_module
            }
        ), mock.patch.object(
            adapter, "_button_pressed", side_effect=[False, False, True]
        ), mock.patch.object(
            adapter,
            "_start_alert",
            return_value=(stop_event, alert_thread)
        ) as start_alert, mock.patch.object(
            adapter, "_stop_alert"
        ) as stop_alert, mock.patch(
            "adapters.out_ev3_operator_alert.time.sleep"
        ), mock.patch(
            "adapters.out_ev3_operator_alert.sys.stdout.flush"
        ):
            shown = adapter.show_fatal_error(lines)

        self.assertTrue(shown)
        console.set_font.assert_called_once_with(
            adapter.CONSOLE_FONT,
            reset_console=True
        )
        self.assertEqual(3, console.text_at.call_count)
        leds.all_off.assert_called_once_with()
        start_alert.assert_called_once_with(leds, sound)
        stop_alert.assert_called_once_with(
            sound,
            leds,
            stop_event,
            alert_thread
        )

    def test_run_startup_alert_safely_stops_when_sound_is_unavailable(self):
        leds = mock.Mock()
        sound = mock.Mock()
        stop_event = mock.Mock()
        stop_event.is_set.return_value = False

        with mock.patch.object(
            Ev3OperatorAlertAdapter,
            "_run_alert_phase",
            side_effect=ImportError()
        ):
            result = Ev3OperatorAlertAdapter._run_startup_alert(
                leds,
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
