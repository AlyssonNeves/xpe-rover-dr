#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 output adapter for operator-visible fatal alerts."""

import sys
import time

from threading import Event, Thread

from infrastructure.ev3.button_feedback import Ev3ButtonFeedback
from infrastructure.ev3.framebuffer_display import create_ev3_display
from infrastructure.ev3.screen_image import (
    cached_screen_path,
    load_monochrome_screen
)
from ports.operator_alert_port import OperatorAlertPort


class Ev3OperatorAlertAdapter(OperatorAlertPort):
    """Displays fatal alerts through the EV3 screen, sound and buttons."""

    BACKGROUND_FILENAME = "Screen 01 - Initialization Error.pbm"

    # The reduced warning symbol leaves a wider area for the main message.
    # Main lines are centered beside the symbol, while the acknowledgement
    # instruction uses the full-width clear strip at the bottom.
    MAIN_TEXT_LEFT = 51
    MAIN_TEXT_RIGHT = 175
    MAIN_TEXT_TOP = 57
    MAIN_TEXT_LINE_HEIGHT = 13
    MAIN_TEXT_FONT_SIZE = 12

    FOOTER_TEXT_LEFT = 3
    FOOTER_TEXT_RIGHT = 175
    FOOTER_TEXT_TOP = 107
    FOOTER_TEXT_FONT_SIZE = 11
    ALERT_FREQUENCY_HZ = 130
    # Matches the approximate 785ms s low-load EV3 heartbeat cycle.
    ALERT_TONE_MS = 385
    ALERT_PAUSE_MS = 400

    BUTTON_POLL_SECONDS = 0.05

    _FONT_CACHE = {}
    _FONT_PATH = None
    _BACKGROUND_IMAGE = None

    # Each LED state remains active during one complete sound cycle:
    # tone duration plus the pause before the next tone.
    ALERT_CYCLE_SECONDS = (
        ALERT_TONE_MS + ALERT_PAUSE_MS
    ) / 1000.0

    @classmethod
    def _asset_path(cls):
        """Returns the absolute path of the initialization-error artwork."""
        return cached_screen_path(cls.BACKGROUND_FILENAME)

    @classmethod
    def _load_background(cls):
        """Loads and reuses the initialization-error background in memory."""
        if cls._BACKGROUND_IMAGE is None:
            cls._BACKGROUND_IMAGE = load_monochrome_screen(
                cls._asset_path(),
                "Initialization-error screen"
            )
        return cls._BACKGROUND_IMAGE.copy()

    @classmethod
    def _load_font(cls, size):
        """Loads and caches the original compact bold TrueType font."""
        cached_font = cls._FONT_CACHE.get(size)
        if cached_font is not None:
            return cached_font

        from PIL import ImageFont  # pylint: disable=import-error

        if cls._FONT_PATH is not None:
            try:
                font = ImageFont.truetype(cls._FONT_PATH, size)
                cls._FONT_CACHE[size] = font
                return font
            except IOError:
                cls._FONT_PATH = None

        for font_name in (
                "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                font = ImageFont.truetype(font_name, size)
                cls._FONT_PATH = font_name
                cls._FONT_CACHE[size] = font
                return font
            except IOError:
                continue

        font = ImageFont.load_default()
        cls._FONT_CACHE[size] = font
        return font

    @classmethod
    def prepare_render_resources(cls):
        """Warms PBM and original fonts before configuration validation."""
        background = cls._load_background()
        background.close()
        cls._load_font(cls.MAIN_TEXT_FONT_SIZE)
        cls._load_font(cls.FOOTER_TEXT_FONT_SIZE)

    @staticmethod
    def _text_width(draw, text, font):
        """Returns text width across supported Pillow versions."""
        try:
            box = draw.textbbox((0, 0), text, font=font)
            return box[2] - box[0]
        except AttributeError:
            return draw.textsize(text, font=font)[0]

    @classmethod
    def _draw_centered_text(cls, draw, text, top, left, right, font):
        """Draws one line centered inside a horizontal safe region."""
        width = cls._text_width(draw, text, font)
        x_position = left + max(0, (right - left - width) // 2)
        draw.text((x_position, top), text, font=font, fill=0)

    @classmethod
    def _draw_error_screen(cls, display, lines):
        """Draws one dynamic initialization error over the base PBM."""
        background = cls._load_background()
        main_font = cls._load_font(cls.MAIN_TEXT_FONT_SIZE)
        footer_font = cls._load_font(cls.FOOTER_TEXT_FONT_SIZE)
        display.image.paste(background, (0, 0))

        main_lines = list(lines[:-1])
        footer_line = lines[-1] if lines else ""

        for index, line in enumerate(main_lines):
            cls._draw_centered_text(
                display.draw,
                line,
                cls.MAIN_TEXT_TOP + index * cls.MAIN_TEXT_LINE_HEIGHT,
                cls.MAIN_TEXT_LEFT,
                cls.MAIN_TEXT_RIGHT,
                main_font
            )

        if footer_line:
            cls._draw_centered_text(
                display.draw,
                footer_line,
                cls.FOOTER_TEXT_TOP,
                cls.FOOTER_TEXT_LEFT,
                cls.FOOTER_TEXT_RIGHT,
                footer_font
            )

        display.update()

    def __init__(self, status_led_port=None, status_led_factory=None,
                 fault_source="configuration"):
        """Configures LED feedback without initializing hardware early."""
        self._status_led_port = status_led_port
        self._status_led_factory = status_led_factory
        self._fault_source = str(fault_source or "configuration")

    def _activate_fault_led(self):
        """Starts the red fault heartbeat only after the screen is visible."""
        try:
            status_led = self._status_led_port
            if status_led is None and self._status_led_factory is not None:
                status_led = self._status_led_factory()
                self._status_led_port = status_led
            if status_led is None:
                return
            status_led.set_fault(self._fault_source, True)
        except (
                IOError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError):
            return

    @classmethod
    def _try_start_alert(cls):
        """Starts the buzzer after display without making sound mandatory."""
        try:
            from ev3dev2.sound import Sound  # pylint: disable=import-error

            sound = Sound()
            stop_event, alert_thread = cls._start_alert(sound)
            return sound, stop_event, alert_thread
        except (
                ImportError, IOError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError):
            return None, None, None

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
    def _run_alert_phase(cls, sound, stop_event):
        """Runs one non-blocking audible alert phase."""
        from ev3dev2.sound import Sound  # pylint: disable=import-error

        sound_process = None
        try:
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
    def _run_startup_alert(cls, sound, stop_event):
        """Repeats the startup-error buzzer until acknowledgement."""
        try:
            while not stop_event.is_set():
                if cls._run_alert_phase(sound, stop_event):
                    break
        except (
                ImportError,
                OSError,
                RuntimeError,
                AttributeError,
                TypeError):
            return

    @classmethod
    def _start_alert(cls, sound):
        """Starts the non-blocking startup-error buzzer."""
        stop_event = Event()
        alert_thread = Thread(
            target=cls._run_startup_alert,
            args=(sound, stop_event)
        )
        alert_thread.daemon = True
        alert_thread.start()
        return stop_event, alert_thread

    @staticmethod
    def _stop_alert_thread(stop_event, alert_thread):
        """Stops the synchronized sound alert thread."""
        if stop_event is not None:
            stop_event.set()
        if alert_thread is not None and alert_thread.is_alive():
            alert_thread.join()

    @classmethod
    def _stop_alert(cls, sound, alert_stop_event=None, alert_thread=None):
        """Stops the startup-error buzzer."""
        cls._stop_alert_thread(alert_stop_event, alert_thread)
        if sound is not None:
            try:
                sound.stop()
            except (OSError, RuntimeError, AttributeError):
                pass

    def show_fatal_error(self, lines):
        """Displays a fatal error and waits for an EV3 button press."""
        sound = None
        alert_stop_event = None
        alert_thread = None
        cleanup_required = False
        try:
            # The screen is the first operator feedback after configuration
            # validation fails.  Do not import sound, touch LEDs or initialize
            # buttons until the framebuffer contains the complete message.
            display = create_ev3_display()
            self._draw_error_screen(display, lines)
            sys.stdout.flush()

            sound, alert_stop_event, alert_thread = self._try_start_alert()
            cleanup_required = sound is not None
            self._activate_fault_led()

            from ev3dev2.button import Button  # pylint: disable=import-error
            buttons = Button()

            # Ignore a button that was already held during startup.
            while self._button_pressed(buttons):
                time.sleep(self.BUTTON_POLL_SECONDS)

            while not self._button_pressed(buttons):
                time.sleep(self.BUTTON_POLL_SECONDS)

            if sound is not None:
                self._stop_alert(
                    sound,
                    alert_stop_event,
                    alert_thread
                )
                cleanup_required = False
                Ev3ButtonFeedback.play(sound)
            return True
        except (
                ImportError, IOError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError):
            return False
        finally:
            if cleanup_required:
                self._stop_alert(
                    sound,
                    alert_stop_event,
                    alert_thread
                )

