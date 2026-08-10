#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 adapter that continuously presents the Rover operation status."""

from datetime import datetime

import socket
import threading
import time

from app.operation_mode_service import coerce_operation_mode
from adapters.out_ev3_operator_alert import Ev3OperatorAlertAdapter
from infrastructure.ev3.button_feedback import Ev3ButtonFeedback
from infrastructure.ev3.framebuffer_display import create_ev3_display
from infrastructure.ev3.screen_image import (
    cached_screen_path,
    load_monochrome_screen
)
from infrastructure.logging.app_logger import AppLogger
from ports.joystick_connection_status_port import (
    JoystickConnectionStatusPort
)
from ports.runtime_component_port import RuntimeComponentPort
from ports.startup_progress_port import StartupProgressPort


class Ev3OperationStatusAdapter(
        RuntimeComponentPort, JoystickConnectionStatusPort,
        StartupProgressPort):
    """Displays five dynamically refreshed status values on the EV3 LCD."""

    REFRESH_SECONDS = 1.0
    BUTTON_POLL_SECONDS = 0.02
    OPERATOR_READY_SPEECH = "Rover D R Online"
    OPERATOR_READY_ESPEAK_OPTIONS = "-a 200 -s 130 -ven-us"
    SCREEN_GENERAL = "general"
    SCREEN_LARGE_MOTORS = "large_motors"
    SCREEN_MEDIUM_MOTORS = "medium_motors"
    STATUS_SCREEN_ORDER = (
        SCREEN_GENERAL, SCREEN_LARGE_MOTORS, SCREEN_MEDIUM_MOTORS
    )
    BACKGROUND_FILENAMES = {
        SCREEN_GENERAL: "Screen 05 - General Status.pbm",
        SCREEN_LARGE_MOTORS: "Screen 06 - Large Motors Status.pbm",
        SCREEN_MEDIUM_MOTORS: "Screen 07 - Medium Motors Status.pbm"
    }
    BACKGROUND_FILENAME = BACKGROUND_FILENAMES[SCREEN_GENERAL]
    STARTUP_BACKGROUND_FILENAME = "Screen 08 - Initialization Status.pbm"
    BLUETOOTH_ERROR_FILENAME = "Screen 03 - Bluetooth Error.pbm"
    EV3_POWER_SUPPLY_ADDRESS = "legoev3-battery"

    # General Status keeps the EV3 block artwork on the left and presents
    # the five operator-relevant values as a single readable text column.
    STATUS_VALUE_FONT_SIZE = 11
    STATUS_BULLET_DIAMETER = 4
    STATUS_BULLET_GAP = 4
    STATUS_BULLET_LEFT = 44
    BATTERY_BULLET_LEFT = 125
    BATTERY_HEADER_POSITION = (133, 58)
    BATTERY_VOLTAGE_POSITION = (125, 71)
    BATTERY_CURRENT_POSITION = (125, 83)
    VALUE_POSITIONS = {
        "ip": (52, 46),
        "command": (52, 58),
        "control": (52, 70),
        "front": (52, 82),
        "drive": (52, 94)
    }

    # Motor screens reuse the exact vertical rhythm of General Status.
    # The template artwork preserves the motor illustration on the left,
    # so the three data columns are shifted to the right safe area.
    MOTOR_STATUS_FONT_SIZE = STATUS_VALUE_FONT_SIZE
    MOTOR_ROW_Y = (46, 58, 70, 82, 94)
    MOTOR_LABEL_RIGHT = 64
    MOTOR_LEFT_CENTER = 95
    MOTOR_RIGHT_CENTER = 149
    MOTOR_CODES = {
        SCREEN_LARGE_MOTORS: ("LLM", "RLM"),
        SCREEN_MEDIUM_MOTORS: ("LMM", "RMM")
    }
    STATUS_CURSOR_BORDER_GAP = 1
    STATUS_CURSOR_ROW_LEFT_BORDER_X = 14
    STATUS_CURSOR_CENTER_Y = 117
    STATUS_CURSOR_HALF_WIDTH = 4
    STATUS_CURSOR_HALF_HEIGHT = 4

    # Bluetooth and startup messages share the same compact typography and
    # safe dynamic-text geometry.
    BLUETOOTH_MESSAGE_LEFT = 51
    BLUETOOTH_MESSAGE_RIGHT = 175
    BLUETOOTH_MESSAGE_TOP = 57
    BLUETOOTH_MESSAGE_LINE_HEIGHT = 13
    BLUETOOTH_MESSAGE_FONT_SIZE = 12
    BLUETOOTH_TIMESTAMP_LEFT = 3
    BLUETOOTH_TIMESTAMP_RIGHT = 175
    BLUETOOTH_TIMESTAMP_TOP = 107
    BLUETOOTH_TIMESTAMP_FONT_SIZE = 11
    STARTUP_INITIAL_MESSAGE = "Initializing Rover control."
    STARTUP_MESSAGE_TOP = 50
    STARTUP_MESSAGE_LINE_HEIGHT = 12
    STARTUP_MAX_LINES = 4
    STARTUP_ERROR_TONE_1_HZ = 220
    STARTUP_ERROR_TONE_1_MS = 180
    STARTUP_ERROR_TONE_2_HZ = 130
    STARTUP_ERROR_TONE_2_MS = 280
    STARTUP_PROMPT_BEEP_COUNT = 3
    STARTUP_PROMPT_FREQUENCY_HZ = 1000
    STARTUP_PROMPT_TONE_MS = 70
    STARTUP_PROMPT_GAP_SECONDS = 0.04

    def __init__(self, operation_mode_service=None, joystick_device_name="",
                 startup_gated=False, motor_query_port=None):
        self.operation_mode_service = operation_mode_service
        self.joystick_device_name = joystick_device_name
        self.motor_query_port = motor_query_port
        self.startup_gated = bool(startup_gated)
        self.start_before_startup_checks = self.startup_gated
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._thread = None
        self._navigation_thread = None
        self._display = None
        self._background = None
        self._status_backgrounds = {}
        self._startup_background = None
        self._bluetooth_error_background = None
        self._font = None
        self._motor_font = None
        self._compact_font = None
        self._bluetooth_message_font = None
        self._bluetooth_timestamp_font = None
        self._display_lock = threading.RLock()
        self._startup_active = self.startup_gated
        self._startup_message = self.STARTUP_INITIAL_MESSAGE
        self._startup_timestamp = self._current_timestamp()
        self._ready_once = not self.startup_gated
        self._bluetooth_error_active = False
        self._bluetooth_error_message = "Joystick unavailable"
        self._bluetooth_retry_seconds = 0.0
        self._bluetooth_error_timestamp = self._current_timestamp()
        self._status_screen = self.SCREEN_GENERAL
        self._buttons = None
        self._navigation_press_latched = False
        self._bluetooth_alert_sound = None
        self._bluetooth_alert_stop_event = None
        self._bluetooth_alert_thread = None

    def start(self):
        """Shows the active status screen before any startup verification."""
        if self._thread is not None and self._thread.is_alive():
            return

        try:
            self._display = create_ev3_display()
            self._load_initial_screen_resources()
            self._buttons = self._create_buttons()
            self._stop_event.clear()
            self._refresh_event.clear()
            self._navigation_press_latched = False
            self._draw_current_screen()
            if self._startup_active:
                self._play_startup_prompt()
            else:
                self._play_operator_prompt_async()
            self._load_deferred_screen_resources()
            self._thread = threading.Thread(
                target=self._run,
                name="Ev3OperationStatusThread"
            )
            self._thread.daemon = True
            self._thread.start()
            self._navigation_thread = threading.Thread(
                target=self._run_navigation,
                name="Ev3OperationStatusNavigationThread"
            )
            self._navigation_thread.daemon = True
            self._navigation_thread.start()
        except ImportError:
            return
        except (IOError, OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
            AppLogger.error(
                "Unable to display EV3 operation-status screen: {0}".format(error)
            )

    def _load_initial_screen_resources(self):
        """Loads only what is needed to paint the first visible screen."""
        if self._startup_active:
            self._startup_background = self._load_startup_background()
            self._bluetooth_message_font = self._load_font(
                self.BLUETOOTH_MESSAGE_FONT_SIZE
            )
            self._bluetooth_timestamp_font = self._load_font(
                self.BLUETOOTH_TIMESTAMP_FONT_SIZE
            )
            return
        self._status_backgrounds = self._load_status_backgrounds()
        self._background = self._status_backgrounds[self.SCREEN_GENERAL]
        self._font = self._load_font(self.STATUS_VALUE_FONT_SIZE)
        self._motor_font = self._load_font(self.MOTOR_STATUS_FONT_SIZE)
        self._compact_font = self._load_font(6)

    def _load_deferred_screen_resources(self):
        """Loads noninitial artwork only after the first screen and prompt."""
        if not self._status_backgrounds:
            self._status_backgrounds = self._load_status_backgrounds()
            self._background = self._status_backgrounds[self.SCREEN_GENERAL]
        if self._startup_background is None:
            self._startup_background = self._load_startup_background()
        if self._bluetooth_error_background is None:
            self._bluetooth_error_background = (
                self._load_bluetooth_error_background()
            )
        if self._font is None:
            self._font = self._load_font(self.STATUS_VALUE_FONT_SIZE)
        if self._motor_font is None:
            self._motor_font = self._load_font(self.MOTOR_STATUS_FONT_SIZE)
        if self._compact_font is None:
            self._compact_font = self._load_font(6)
        if self._bluetooth_message_font is None:
            self._bluetooth_message_font = self._load_font(
                self.BLUETOOTH_MESSAGE_FONT_SIZE
            )
        if self._bluetooth_timestamp_font is None:
            self._bluetooth_timestamp_font = self._load_font(
                self.BLUETOOTH_TIMESTAMP_FONT_SIZE
            )

    @classmethod
    def _play_startup_prompt(cls):
        """Matches the three-beep prompt used when Front/Drive opens."""
        try:
            from ev3dev2.sound import Sound  # pylint: disable=import-error

            sound = Sound()
            for beep_index in range(cls.STARTUP_PROMPT_BEEP_COUNT):
                sound.tone(
                    cls.STARTUP_PROMPT_FREQUENCY_HZ,
                    cls.STARTUP_PROMPT_TONE_MS,
                    play_type=Sound.PLAY_WAIT_FOR_COMPLETE
                )
                if beep_index < cls.STARTUP_PROMPT_BEEP_COUNT - 1:
                    time.sleep(cls.STARTUP_PROMPT_GAP_SECONDS)
        except (
                ImportError, IOError, OSError, RuntimeError,
                AttributeError, TypeError, ValueError) as error:
            AppLogger.warning(
                "Unable to emit Initialization Status prompt beeps: {0}".format(
                    error
                )
            )

    @classmethod
    def _play_operator_prompt_async(cls):
        """Emits the ready prompt without delaying joystick activation."""
        thread = threading.Thread(
            target=cls._play_operator_prompt,
            name="Ev3OperationReadyPromptThread"
        )
        thread.daemon = True
        thread.start()

    @classmethod
    def _play_operator_prompt(cls):
        """Announces Rover readiness after the status screen is visible."""
        try:
            from ev3dev2.sound import Sound  # pylint: disable=import-error

            sound = Sound()
            sound.speak(
                cls.OPERATOR_READY_SPEECH,
                espeak_opts=cls.OPERATOR_READY_ESPEAK_OPTIONS,
                play_type=Sound.PLAY_WAIT_FOR_COMPLETE
            )
        except (
                ImportError, IOError, OSError, RuntimeError,
                AttributeError, TypeError, ValueError) as error:
            # The spoken announcement is informational and must never prevent
            # status display or Rover control when audio is unavailable.
            AppLogger.warning(
                "Unable to speak Rover ready announcement: {0}".format(
                    error
                )
            )

    def stop(self):
        """Stops periodic status updates, navigation and error audio."""
        self._stop_bluetooth_error_alert()
        self._stop_event.set()
        self._refresh_event.set()
        current = threading.current_thread()
        if self._thread is not None and self._thread is not current:
            self._thread.join(timeout=2.0)
        if (self._navigation_thread is not None and
                self._navigation_thread is not current):
            self._navigation_thread.join(timeout=2.0)

    def _run(self):
        """Refreshes status values independently from button detection."""
        while not self._stop_event.is_set():
            self._refresh_event.wait(self.REFRESH_SECONDS)
            self._refresh_event.clear()
            if self._stop_event.is_set():
                break
            try:
                self._refresh_status_values()
            except (
                    IOError, OSError, RuntimeError, AttributeError, TypeError,
                    ValueError) as error:
                AppLogger.error(
                    "Unable to update EV3 operation-status screen: {0}".format(error)
                )

    def _run_navigation(self):
        """Detects button press edges without waiting for button release."""
        while not self._stop_event.wait(self.BUTTON_POLL_SECONDS):
            try:
                self._poll_status_navigation()
            except (
                    IOError, OSError, RuntimeError, AttributeError, TypeError,
                    ValueError) as error:
                AppLogger.error(
                    "Unable to read EV3 status navigation buttons: {0}".format(
                        error
                    )
                )

    @classmethod
    def _asset_path(cls, screen_name=None):
        active_screen = screen_name or cls.SCREEN_GENERAL
        return cached_screen_path(cls.BACKGROUND_FILENAMES[active_screen])

    @classmethod
    def _load_background(cls, screen_name=None):
        """Loads one ready-to-use monochrome status screen."""
        active_screen = screen_name or cls.SCREEN_GENERAL
        return load_monochrome_screen(
            cls._asset_path(active_screen),
            "Operation-status screen"
        )

    @classmethod
    def _load_status_backgrounds(cls):
        return {
            screen_name: cls._load_background(screen_name)
            for screen_name in cls.STATUS_SCREEN_ORDER
        }

    @staticmethod
    def _create_buttons():
        try:
            from ev3dev2.button import Button  # pylint: disable=import-error
            return Button()
        except ImportError:
            return None

    def set_motor_query_port(self, motor_query_port):
        """Attaches the read-only motor telemetry source after composition."""
        self.motor_query_port = motor_query_port

    @classmethod
    def _load_startup_background(cls):
        """Loads the dedicated initialization-status artwork for progress."""
        return load_monochrome_screen(
            cached_screen_path(cls.STARTUP_BACKGROUND_FILENAME),
            "Initialization-progress screen"
        )

    @classmethod
    def _load_bluetooth_error_background(cls):
        """Loads the ready-to-use Bluetooth error screen."""
        return load_monochrome_screen(
            cached_screen_path(cls.BLUETOOTH_ERROR_FILENAME),
            "Bluetooth-error screen"
        )

    @staticmethod
    def _load_font(size=8):
        from PIL import ImageFont  # pylint: disable=import-error

        # The condensed face is closer to the compact lettering used in the
        # background artwork and avoids excessive spacing between characters.
        for font_name in (
                "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(font_name, size)
            except IOError:
                continue
        return ImageFont.load_default()

    def show_startup_progress(self, message):
        """Shows one timed initialization step on the status screen."""
        with self._display_lock:
            self._startup_active = True
            self._bluetooth_error_active = False
            self._startup_message = str(
                message or self.STARTUP_INITIAL_MESSAGE
            )
            self._startup_timestamp = self._current_timestamp()
            if self._display is not None:
                self._draw_current_screen_locked()

    def show_startup_error(self, message):
        """Shows a recoverable startup error and emits a short error buzzer."""
        self.show_startup_progress(message)
        self._play_startup_error_tone_async()

    @classmethod
    def _play_startup_error_tone_async(cls):
        """Emits the startup-error buzzer without delaying the retry cycle."""
        thread = threading.Thread(
            target=cls._play_startup_error_tone,
            name="Ev3StartupErrorToneThread"
        )
        thread.daemon = True
        thread.start()

    @classmethod
    def _play_startup_error_tone(cls):
        """Plays a short descending two-tone startup-error signal."""
        try:
            from ev3dev2.sound import Sound  # pylint: disable=import-error

            sound = Sound()
            sound.tone(
                cls.STARTUP_ERROR_TONE_1_HZ,
                cls.STARTUP_ERROR_TONE_1_MS,
                play_type=Sound.PLAY_WAIT_FOR_COMPLETE
            )
            sound.tone(
                cls.STARTUP_ERROR_TONE_2_HZ,
                cls.STARTUP_ERROR_TONE_2_MS,
                play_type=Sound.PLAY_WAIT_FOR_COMPLETE
            )
        except (
                ImportError, IOError, OSError, RuntimeError,
                AttributeError, TypeError, ValueError) as error:
            # Audio is secondary feedback and must never block retries.
            AppLogger.warning(
                "Unable to play Rover startup-error tone: {0}".format(error)
            )

    def _start_bluetooth_error_alert(self):
        """Starts the same repeating error buzzer used for token faults."""
        if self._bluetooth_alert_sound is not None:
            return
        sound, stop_event, alert_thread = (
            Ev3OperatorAlertAdapter._try_start_alert()
        )
        self._bluetooth_alert_sound = sound
        self._bluetooth_alert_stop_event = stop_event
        self._bluetooth_alert_thread = alert_thread

    def _stop_bluetooth_error_alert(self):
        """Stops an active Bluetooth-error buzzer immediately."""
        sound = self._bluetooth_alert_sound
        stop_event = self._bluetooth_alert_stop_event
        alert_thread = self._bluetooth_alert_thread
        self._bluetooth_alert_sound = None
        self._bluetooth_alert_stop_event = None
        self._bluetooth_alert_thread = None
        if sound is not None:
            Ev3OperatorAlertAdapter._stop_alert(
                sound, stop_event, alert_thread
            )

    def show_joystick_connection_error(self, message, retry_seconds):
        """Shows Bluetooth error and starts the token-style error buzzer."""
        start_alert = False
        with self._display_lock:
            start_alert = not self._bluetooth_error_active
            self._startup_active = False
            self._bluetooth_error_active = True
            self._bluetooth_error_message = str(
                message or "Joystick unavailable"
            )
            self._bluetooth_retry_seconds = max(
                0.0, float(retry_seconds)
            )
            self._bluetooth_error_timestamp = self._current_timestamp()
            if self._display is not None:
                self._draw_current_screen_locked()
        if start_alert:
            self._start_bluetooth_error_alert()

    def show_joystick_connected(self, device_name):
        """Stops Bluetooth alert and restores status after reconnection."""
        del device_name
        self._stop_bluetooth_error_alert()
        should_prompt = False
        with self._display_lock:
            should_prompt = not self._ready_once
            self._ready_once = True
            self._startup_active = False
            self._bluetooth_error_active = False
            if self._display is not None:
                self._draw_current_screen_locked()
        if should_prompt:
            self._play_operator_prompt_async()

    def _refresh_status_values(self):
        """Reads telemetry outside the display lock, then paints if still current."""
        with self._display_lock:
            if self._startup_active or self._bluetooth_error_active:
                return
            screen_name = self._status_screen

        if screen_name == self.SCREEN_GENERAL:
            values = self._read_values()
        else:
            values = self._read_motor_status_values(screen_name)

        with self._display_lock:
            if (self._startup_active or self._bluetooth_error_active or
                    self._status_screen != screen_name):
                return
            if screen_name == self.SCREEN_GENERAL:
                self._draw_general_status_locked(values=values)
            else:
                self._draw_motor_status_locked(screen_name, values=values)

    def _draw_current_screen(self):
        with self._display_lock:
            self._draw_current_screen_locked()

    def _draw_current_screen_locked(self):
        if self._startup_active:
            self._draw_startup_progress_locked()
        elif self._bluetooth_error_active:
            self._draw_bluetooth_error_locked()
        else:
            self._draw_status_locked()

    def _draw_status_locked(self):
        if self._status_screen == self.SCREEN_GENERAL:
            self._draw_general_status_locked()
        else:
            self._draw_motor_status_locked(self._status_screen)

    def _draw_general_status_locked(self, values=None):
        values = values if values is not None else self._read_values()
        background = self._status_backgrounds.get(
            self.SCREEN_GENERAL, self._background
        )
        self._display.image.paste(background, (0, 0))
        for field_name, position in self.VALUE_POSITIONS.items():
            self._display.draw.ellipse(
                self._status_bullet_bbox(position),
                fill=0
            )
            self._display.draw.text(
                position,
                values[field_name],
                font=self._font,
                fill=0
            )
        self._draw_battery_status(values)
        self._draw_status_cursor()
        self._display.update()

    def _draw_battery_status(self, values):
        """Draws compact EV3 battery voltage and current on the right."""
        header_position = self.BATTERY_HEADER_POSITION
        bullet_top = header_position[1] + 3
        self._display.draw.ellipse(
            (
                self.BATTERY_BULLET_LEFT,
                bullet_top,
                self.BATTERY_BULLET_LEFT + self.STATUS_BULLET_DIAMETER - 1,
                bullet_top + self.STATUS_BULLET_DIAMETER - 1
            ),
            fill=0
        )
        self._display.draw.text(
            header_position, "Bat.", font=self._font, fill=0
        )
        self._display.draw.text(
            self.BATTERY_VOLTAGE_POSITION,
            values.get("battery_voltage", "N/A"),
            font=self._font,
            fill=0
        )
        self._display.draw.text(
            self.BATTERY_CURRENT_POSITION,
            values.get("battery_current", "N/A"),
            font=self._font,
            fill=0
        )

    def _draw_motor_status_locked(self, screen_name, values=None):
        background = self._status_backgrounds.get(screen_name, self._background)
        self._display.image.paste(background, (0, 0))
        values = (
            values if values is not None
            else self._read_motor_status_values(screen_name)
        )

        header_y, speed_y, duty_y, position_y, state_y = self.MOTOR_ROW_Y
        self._draw_motor_centered("Left", self.MOTOR_LEFT_CENTER, header_y)
        self._draw_motor_centered("Right", self.MOTOR_RIGHT_CENTER, header_y)

        rows = (
            ("Speed", values["left"]["speed"], values["right"]["speed"], speed_y),
            ("Cycle", values["left"]["duty_cycle"],
             values["right"]["duty_cycle"], duty_y),
            ("Pos.", values["left"]["position"],
             values["right"]["position"], position_y),
            ("State", values["left"]["state"], values["right"]["state"], state_y)
        )
        for label, left_value, right_value, y_position in rows:
            self._draw_motor_label_right_aligned(label, y_position)
            self._draw_motor_centered(
                left_value, self.MOTOR_LEFT_CENTER, y_position
            )
            self._draw_motor_centered(
                right_value, self.MOTOR_RIGHT_CENTER, y_position
            )
        self._draw_status_cursor()
        self._display.update()

    def _draw_status_cursor(self):
        cursor_tip_x = (
            self.STATUS_CURSOR_ROW_LEFT_BORDER_X -
            self.STATUS_CURSOR_BORDER_GAP
        )
        center_x = cursor_tip_x - self.STATUS_CURSOR_HALF_WIDTH
        center_y = self.STATUS_CURSOR_CENTER_Y
        self._display.draw.polygon(
            (
                (center_x - self.STATUS_CURSOR_HALF_WIDTH,
                 center_y - self.STATUS_CURSOR_HALF_HEIGHT),
                (center_x - self.STATUS_CURSOR_HALF_WIDTH,
                 center_y + self.STATUS_CURSOR_HALF_HEIGHT),
                (center_x + self.STATUS_CURSOR_HALF_WIDTH, center_y)
            ),
            fill=0
        )

    def _draw_motor_label_right_aligned(self, text, y_position):
        width = self._text_width(self._display.draw, text, self._motor_font)
        self._display.draw.text(
            (self.MOTOR_LABEL_RIGHT - width, y_position),
            text, font=self._motor_font, fill=0
        )

    def _draw_motor_centered(self, text, center_x, y_position):
        width = self._text_width(self._display.draw, text, self._motor_font)
        self._display.draw.text(
            (int(center_x - width // 2), y_position),
            text, font=self._motor_font, fill=0
        )

    def _poll_status_navigation(self):
        """Switches screens on the press edge, never on the release edge."""
        if self._buttons is None:
            return False

        button_name = self._pressed_navigation_button(self._buttons)
        if button_name is None:
            self._navigation_press_latched = False
            return False
        if self._navigation_press_latched:
            return False

        self._navigation_press_latched = True
        with self._display_lock:
            if self._startup_active or self._bluetooth_error_active:
                return False
            self._status_screen = self._adjacent_status_screen(
                self._status_screen, button_name
            )
            self._draw_status_background_locked(self._status_screen)

        # Uses the same short confirmation beep as Local/Remote selection.
        Ev3ButtonFeedback.play()

        # Telemetry may involve slower I/O. Request it only after the new
        # screen is already visible, and let the refresh thread perform it.
        self._refresh_event.set()
        return True

    def _draw_status_background_locked(self, screen_name):
        """Shows a selected status screen immediately, without telemetry I/O."""
        background = self._status_backgrounds.get(screen_name, self._background)
        self._display.image.paste(background, (0, 0))
        self._draw_status_cursor()
        self._display.update()

    @classmethod
    def _pressed_navigation_button(cls, buttons):
        if cls._navigation_button_pressed(buttons, "left"):
            return "left"
        if cls._navigation_button_pressed(buttons, "right"):
            return "right"
        return None

    @staticmethod
    def _navigation_button_pressed(buttons, name):
        try:
            return bool(getattr(buttons, name, False))
        except (OSError, RuntimeError, AttributeError):
            return False

    @classmethod
    def _adjacent_status_screen(cls, current_screen, button_name):
        order = cls.STATUS_SCREEN_ORDER
        try:
            index = order.index(current_screen)
        except ValueError:
            index = 0
        step = -1 if button_name == "left" else 1
        return order[(index + step) % len(order)]

    def _read_motor_status_values(self, screen_name):
        left_code, right_code = self.MOTOR_CODES[screen_name]
        return {
            "left": self._motor_dynamic_values(self._read_motor(left_code)),
            "right": self._motor_dynamic_values(self._read_motor(right_code))
        }

    def _read_motor(self, motor_code):
        if self.motor_query_port is None:
            return {}
        try:
            return self.motor_query_port.read_motor(motor_code) or {}
        except (IOError, OSError, RuntimeError, AttributeError, TypeError, ValueError):
            return {}

    @classmethod
    def _motor_dynamic_values(cls, motor):
        return {
            "speed": cls._format_engineering_value(
                motor.get("speed"), motor.get("speed_sp"), "°/s"
            ),
            "duty_cycle": cls._format_engineering_value(
                motor.get("duty_cycle"), motor.get("duty_cycle_sp"), "%"
            ),
            "position": cls._format_engineering_value(
                motor.get("position"), None, "°"
            ),
            "state": cls._format_motor_state(
                motor.get("state"), motor.get("motion_state")
            )
        }

    @classmethod
    def _format_engineering_value(cls, primary, fallback, unit):
        value = primary if primary is not None else fallback
        if value is None:
            return "-"
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return str(value)
        if numeric_value.is_integer():
            numeric_text = "{0:+d}".format(int(numeric_value))
        else:
            numeric_text = "{0:+.1f}".format(numeric_value)
        return "{0} {1}".format(numeric_text, unit)

    @staticmethod
    def _format_motor_state(primary, fallback=None):
        value = primary
        if isinstance(value, (list, tuple, set)):
            items = [str(item) for item in value if str(item)]
            value = items[0] if items else None
        if value in (None, ""):
            value = fallback
        if isinstance(value, (list, tuple, set)):
            items = [str(item) for item in value if str(item)]
            value = items[0] if items else None
        if value in (None, ""):
            return "stopped"
        return str(value).lower()

    @classmethod
    def _status_bullet_bbox(cls, position):
        """Returns the filled bullet bounds rendered before one status line."""
        y_position = position[1]
        left = cls.STATUS_BULLET_LEFT
        top = y_position + 4
        right = left + cls.STATUS_BULLET_DIAMETER - 1
        bottom = top + cls.STATUS_BULLET_DIAMETER - 1
        return (left, top, right, bottom)

    def _draw_startup_progress_locked(self):
        self._display.image.paste(self._startup_background, (0, 0))
        lines = self._wrapped_message_lines(
            self._display.draw,
            self._startup_message,
            self._bluetooth_message_font,
            self.BLUETOOTH_MESSAGE_RIGHT - self.BLUETOOTH_MESSAGE_LEFT,
            self.STARTUP_MAX_LINES
        )
        for index, line in enumerate(lines):
            self._draw_centered_text(
                self._display.draw,
                line,
                self.STARTUP_MESSAGE_TOP +
                index * self.STARTUP_MESSAGE_LINE_HEIGHT,
                self.BLUETOOTH_MESSAGE_LEFT,
                self.BLUETOOTH_MESSAGE_RIGHT,
                self._bluetooth_message_font
            )
        self._draw_centered_text(
            self._display.draw,
            self._startup_timestamp,
            self.BLUETOOTH_TIMESTAMP_TOP,
            self.BLUETOOTH_TIMESTAMP_LEFT,
            self.BLUETOOTH_TIMESTAMP_RIGHT,
            self._bluetooth_timestamp_font
        )
        self._display.update()

    def _draw_bluetooth_error_locked(self):
        self._display.image.paste(self._bluetooth_error_background, (0, 0))
        lines = self._bluetooth_message_lines(
            self._bluetooth_error_message,
            self._bluetooth_retry_seconds
        )
        for index, line in enumerate(lines):
            self._draw_centered_text(
                self._display.draw,
                line,
                self.BLUETOOTH_MESSAGE_TOP +
                index * self.BLUETOOTH_MESSAGE_LINE_HEIGHT,
                self.BLUETOOTH_MESSAGE_LEFT,
                self.BLUETOOTH_MESSAGE_RIGHT,
                self._bluetooth_message_font
            )
        self._draw_centered_text(
            self._display.draw,
            self._bluetooth_error_timestamp,
            self.BLUETOOTH_TIMESTAMP_TOP,
            self.BLUETOOTH_TIMESTAMP_LEFT,
            self.BLUETOOTH_TIMESTAMP_RIGHT,
            self._bluetooth_timestamp_font
        )
        self._display.update()

    @classmethod
    def _wrapped_message_lines(cls, draw, message, font, maximum_width,
                               maximum_lines):
        """Wraps a progress message to the EV3 safe text area."""
        raw_message = str(message or "")
        explicit_lines = cls._explicit_message_lines(
            raw_message, maximum_lines
        )
        if explicit_lines is not None:
            return explicit_lines

        words = raw_message.split()
        if not words:
            return (cls.STARTUP_INITIAL_MESSAGE,)

        lines = []
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if cls._text_width(draw, candidate, font) <= maximum_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) >= maximum_lines:
                break

        if current and len(lines) < maximum_lines:
            lines.append(current)

        cls._append_truncation_marker(
            draw, lines, words, font, maximum_width, maximum_lines
        )
        return tuple(lines)

    @staticmethod
    def _explicit_message_lines(raw_message, maximum_lines):
        """Returns preserved explicit lines when the message supplies them."""
        explicit_lines = [
            line.strip() for line in raw_message.splitlines()
            if line.strip()
        ]
        if len(explicit_lines) > 1:
            return tuple(explicit_lines[:maximum_lines])
        return None

    @classmethod
    def _append_truncation_marker(cls, draw, lines, words, font,
                                  maximum_width, maximum_lines):
        """Marks a wrapped final line when part of the message was omitted."""
        if len(lines) != maximum_lines or not words:
            return
        if " ".join(lines) == " ".join(words):
            return

        last = lines[-1]
        while last and cls._text_width(
                draw, last + "...", font) > maximum_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."

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

    @staticmethod
    def _current_timestamp():
        """Returns the operator-visible timestamp for the current instant."""
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    @staticmethod
    def _bluetooth_message_lines(message, retry_seconds=0.0):
        normalized = str(message or "Joystick unavailable").lower()
        if "trying to connect" in normalized:
            return ("Joystick", "not found", "Connecting...")
        if "lost" in normalized:
            return ("Connection lost", "New search", "in {0:.0f}s".format(
                max(0.0, float(retry_seconds))
            ))
        if "new search" in normalized or "still not found" in normalized:
            return ("Still not found", "New search", "in {0:.0f}s".format(
                max(0.0, float(retry_seconds))
            ))
        return ("Joystick", "not found", "Searching...")

    def _read_values(self):
        selected_mode = coerce_operation_mode(self.operation_mode_service)
        battery_voltage, battery_current = self._read_battery_measurements()
        return {
            "ip": self._read_ip_address(),
            "command": self._display_value(selected_mode.command),
            "control": self._display_value(selected_mode.control or "N/A"),
            "front": self._display_value(selected_mode.front or "N/A"),
            "drive": self._display_drive_value(
                selected_mode.drive, selected_mode.centric,
                selected_mode.differential_mode
            ),
            "battery_voltage": battery_voltage,
            "battery_current": battery_current
        }

    @classmethod
    def _display_drive_value(cls, drive, centric, differential_mode=None):
        """Combines drive and its active detail into one compact status line."""
        if drive is None:
            return "N/A"
        if str(drive).upper() == "DIFFERENTIAL":
            if differential_mode is None:
                return "Differential"
            mode_label = str(differential_mode).replace("R-BOGIE", "R-Bogie")
            if mode_label == "DUOWHELL":
                mode_label = "Duowhell"
            return "Dif. {0}".format(mode_label)
        if str(drive).upper() != "MECANUM":
            return cls._display_value(drive)
        if centric is None:
            return "Mecanum"
        return "Mec. {0}".format(cls._display_value(centric))

    @staticmethod
    def _display_value(value):
        """Preserves English labels while applying the established title case."""
        if value == "N/A":
            return value
        return str(value).capitalize()

    @staticmethod
    def _read_ip_address():
        connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            connection.connect(("8.8.8.8", 80))
            return connection.getsockname()[0]
        except (IOError, OSError):
            try:
                return socket.gethostbyname(socket.gethostname())
            except (IOError, OSError):
                return "Unavailable"
        finally:
            connection.close()

    def _read_joystick_status(self):
        try:
            import evdev  # pylint: disable=import-error

            for path in evdev.list_devices():
                device = evdev.InputDevice(path)
                try:
                    if device.name == self.joystick_device_name:
                        return "Connected"
                finally:
                    device.close()
        except (ImportError, IOError, OSError, RuntimeError):
            pass
        return "Disconnected"

    @classmethod
    def _read_battery_measurements(cls):
        """Returns EV3 battery voltage in V and current in mA for display."""
        try:
            from ev3dev2 import DeviceNotFound  # pylint: disable=import-error
            from ev3dev2.power import PowerSupply  # pylint: disable=import-error
        except ImportError:
            return "N/A", "N/A"

        try:
            supply = PowerSupply(address=cls.EV3_POWER_SUPPLY_ADDRESS)
            measured_volts = float(supply.measured_volts)
            measured_milliamps = float(supply.measured_amps) * 1000.0
            return (
                "{0:.2f} V".format(measured_volts),
                "{0:.0f} mA".format(measured_milliamps)
            )
        except (
                IOError, OSError, RuntimeError, DeviceNotFound,
                AttributeError, TypeError, ValueError):
            # Battery telemetry is informational and must never interrupt
            # Rover control if the Linux power-supply device is unavailable.
            return "N/A", "N/A"

    @classmethod
    def _read_battery_percentage(cls):
        try:
            from ev3dev2 import DeviceNotFound  # pylint: disable=import-error
            from ev3dev2.power import PowerSupply  # pylint: disable=import-error

            # Bluetooth controllers may also register a Linux power-supply
            # device. Address the EV3 battery explicitly so ev3dev2 never
            # binds this status field to a transient joystick battery.
            supply = PowerSupply(address=cls.EV3_POWER_SUPPLY_ADDRESS)
            measured = float(supply.measured_volts)
            maximum = float(supply.max_volts)
            if maximum <= 0:
                return "Unavailable"
            percentage = max(0, min(100, int(round(measured * 100.0 / maximum))))
            return "{0}%".format(percentage)
        except (
                ImportError, IOError, OSError, RuntimeError, DeviceNotFound,
                AttributeError, TypeError, ValueError):
            # The operation-status display is informational. A missing or
            # disconnecting power-supply device must not stop Rover control.
            return "Unavailable"
