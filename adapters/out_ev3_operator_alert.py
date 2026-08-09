#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 output adapter for operator-visible fatal alerts."""

import sys
import time

from threading import Event, Thread

from ports.operator_alert_port import OperatorAlertPort


class Ev3OperatorAlertAdapter(OperatorAlertPort):
    """Displays fatal alerts through the EV3 screen, LEDs, sound and buttons."""

    CONSOLE_FONT = "Lat15-TerminusBold14.psf.gz"

    ALERT_FREQUENCY_HZ = 130
    ALERT_TONE_MS = 450
    ALERT_PAUSE_MS = 100

    BUTTON_POLL_SECONDS = 0.05

    # Each LED state remains active during one complete sound cycle:
    # tone duration plus the pause before the next tone.
    ALERT_CYCLE_SECONDS = (
        ALERT_TONE_MS + ALERT_PAUSE_MS
    ) / 1000.0

    @staticmethod
    def _button_pressed(buttons):
        """Returns True when any physical EV3 brick button is pressed."""
        try:
            if buttons.any():
                return True
        except (OSError, RuntimeError, AttributeError):
            pass

        for name in (
                "up", "down", "left", "right", "enter", "backspace"):
            try:
                if bool(getattr(buttons, name)):
                    return True
            except (OSError, RuntimeError, AttributeError):
                continue

        return False

    @staticmethod
    def _terminate_sound_process(sound_process):
        """Terminates a non-blocking EV3 sound process when still active."""
        if sound_process is None:
            return

        try:
            if sound_process.poll() is None:
                sound_process.terminate()
                sound_process.wait()
        except (OSError, RuntimeError, AttributeError):
            pass

    @classmethod
    def _run_alert_phase(
            cls,
            leds,
            sound,
            stop_event,
            left_color,
            right_color):
        """Runs one synchronized sound and LED alert phase."""
        from ev3dev2.sound import Sound  # pylint: disable=import-error

        sound_process = None

        try:
            leds.set_color("LEFT", left_color)
            leds.set_color("RIGHT", right_color)

            sound_process = sound.tone(
                cls.ALERT_FREQUENCY_HZ,
                cls.ALERT_TONE_MS,
                play_type=Sound.PLAY_NO_WAIT_FOR_COMPLETE
            )

            if stop_event.wait(cls.ALERT_CYCLE_SECONDS):
                cls._terminate_sound_process(sound_process)
                return True

            return False
        except (OSError, RuntimeError, AttributeError, TypeError):
            cls._terminate_sound_process(sound_process)
            raise

    @classmethod
    def _run_startup_alert(cls, leds, sound, stop_event):
        """Runs synchronized sound and red LED alerts until stopped."""
        try:
            while not stop_event.is_set():
                if cls._run_alert_phase(
                        leds,
                        sound,
                        stop_event,
                        "RED",
                        "BLACK"):
                    break

                if cls._run_alert_phase(
                        leds,
                        sound,
                        stop_event,
                        "BLACK",
                        "RED"):
                    break
        except (
                ImportError,
                OSError,
                RuntimeError,
                AttributeError,
                TypeError):
            # Failure of the secondary audible/visual alert must not prevent
            # the screen message and button acknowledgement from operating.
            return

    @classmethod
    def _start_alert(cls, leds, sound):
        """Starts the synchronized sound and LED alert."""
        stop_event = Event()

        alert_thread = Thread(
            target=cls._run_startup_alert,
            args=(leds, sound, stop_event)
        )
        alert_thread.daemon = True
        alert_thread.start()

        return stop_event, alert_thread

    @staticmethod
    def _stop_alert_thread(stop_event, alert_thread):
        """Stops the synchronized sound and LED alert thread."""
        if stop_event is not None:
            stop_event.set()

        if alert_thread is not None and alert_thread.is_alive():
            alert_thread.join()

    @classmethod
    def _stop_alert(
            cls,
            sound,
            leds,
            alert_stop_event=None,
            alert_thread=None):
        """Stops the startup alert and turns off the EV3 status LEDs."""
        cls._stop_alert_thread(alert_stop_event, alert_thread)

        if sound is not None:
            try:
                sound.stop()
            except (OSError, RuntimeError, AttributeError):
                pass

        if leds is not None:
            try:
                leds.all_off()
            except (OSError, RuntimeError, AttributeError):
                pass

    def show_fatal_error(self, lines):
        """Displays a fatal error and waits for an EV3 button press."""
        try:
            from ev3dev2.button import Button  # pylint: disable=import-error
            from ev3dev2.console import Console  # pylint: disable=import-error
            from ev3dev2.led import Leds  # pylint: disable=import-error
            from ev3dev2.sound import Sound  # pylint: disable=import-error

            console = Console()
            console.set_font(self.CONSOLE_FONT, reset_console=True)

            for row, line in enumerate(lines, start=1):
                console.text_at(
                    line,
                    column=1,
                    row=row,
                    reset_console=False,
                    inverse=(row <= 2)
                )

            sys.stdout.flush()

            leds = Leds()
            sound = Sound()
            buttons = Button()

            alert_stop_event = None
            alert_thread = None

            try:
                leds.all_off()
                alert_stop_event, alert_thread = self._start_alert(
                    leds,
                    sound
                )

                # Ignore a button that was already held during startup.
                while self._button_pressed(buttons):
                    time.sleep(self.BUTTON_POLL_SECONDS)

                while not self._button_pressed(buttons):
                    time.sleep(self.BUTTON_POLL_SECONDS)
            finally:
                self._stop_alert(
                    sound,
                    leds,
                    alert_stop_event,
                    alert_thread
                )

            return True
        except (ImportError, OSError, RuntimeError, AttributeError):
            return False
