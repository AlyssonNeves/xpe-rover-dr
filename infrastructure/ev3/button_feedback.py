#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Best-effort audible feedback for EV3 brick button presses."""

from infrastructure.logging.app_logger import AppLogger


class Ev3ButtonFeedback(object):
    """Emits one short confirmation tone without disrupting navigation."""

    FREQUENCY_HZ = 1200
    TONE_MS = 40

    @classmethod
    def play(cls, sound=None):
        """Plays one short beep and returns whether it was emitted."""
        try:
            from ev3dev2.sound import Sound  # pylint: disable=import-error

            active_sound = sound if sound is not None else Sound()
            active_sound.tone(
                cls.FREQUENCY_HZ,
                cls.TONE_MS,
                play_type=Sound.PLAY_WAIT_FOR_COMPLETE
            )
            return True
        except (
                ImportError, IOError, OSError, RuntimeError,
                AttributeError, TypeError) as error:
            AppLogger.warning(
                "Unable to emit EV3 button beep: {0}".format(error)
            )
            return False
