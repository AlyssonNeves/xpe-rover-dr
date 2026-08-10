#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for audible EV3 brick-button feedback."""

import sys
import types
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from infrastructure.ev3.button_feedback import Ev3ButtonFeedback


class Ev3ButtonFeedbackTests(unittest.TestCase):
    def test_play_emits_one_short_blocking_tone(self):
        sound = mock.Mock()
        sound_class = mock.Mock()
        sound_class.PLAY_WAIT_FOR_COMPLETE = 7
        sound_module = types.ModuleType("ev3dev2.sound")
        sound_module.Sound = sound_class
        ev3dev2_module = types.ModuleType("ev3dev2")

        with mock.patch.dict(
                sys.modules,
                {"ev3dev2": ev3dev2_module, "ev3dev2.sound": sound_module}):
            emitted = Ev3ButtonFeedback.play(sound)

        self.assertTrue(emitted)
        sound.tone.assert_called_once_with(
            Ev3ButtonFeedback.FREQUENCY_HZ,
            Ev3ButtonFeedback.TONE_MS,
            play_type=7
        )

    def test_play_creates_sound_when_instance_is_not_supplied(self):
        sound = mock.Mock()
        sound_class = mock.Mock(return_value=sound)
        sound_class.PLAY_WAIT_FOR_COMPLETE = 3
        sound_module = types.ModuleType("ev3dev2.sound")
        sound_module.Sound = sound_class
        ev3dev2_module = types.ModuleType("ev3dev2")

        with mock.patch.dict(
                sys.modules,
                {"ev3dev2": ev3dev2_module, "ev3dev2.sound": sound_module}):
            emitted = Ev3ButtonFeedback.play()

        self.assertTrue(emitted)
        sound_class.assert_called_once_with()
        sound.tone.assert_called_once_with(
            Ev3ButtonFeedback.FREQUENCY_HZ,
            Ev3ButtonFeedback.TONE_MS,
            play_type=3
        )

    def test_play_does_not_interrupt_navigation_when_sound_is_unavailable(self):
        with mock.patch.dict(
                sys.modules,
                {"ev3dev2": None, "ev3dev2.sound": None}), mock.patch(
                "infrastructure.ev3.button_feedback.AppLogger.warning") as warning:
            emitted = Ev3ButtonFeedback.play()

        self.assertFalse(emitted)
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
