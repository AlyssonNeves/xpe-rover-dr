#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 adapter that periodically presents Rover operational status."""

import socket
import threading

from infrastructure.ev3.screen_image import load_monochrome_screen, screen_asset_path
from infrastructure.logging.app_logger import AppLogger


class Ev3OperationStatusAdapter(object):
    """Displays battery, IP, joystick and current Command/Control values."""

    REFRESH_SECONDS = 1.0
    BACKGROUND_FILENAME = "Screen 05 - General Status.pbm"
    EV3_POWER_SUPPLY_ADDRESS = "legoev3-battery"
    OPERATOR_READY_SPEECH = "Rover D R Online"
    OPERATOR_READY_ESPEAK_OPTIONS = "-a 200 -s 130 -ven-us"

    VALUE_POSITIONS = {
        "battery": (69, 54),
        "ip": (69, 71),
        "joystick": (69, 88),
        "command": (133, 54),
        "control": (133, 71)
    }
    COMPACT_VALUE_FIELDS = frozenset(("battery", "ip", "joystick"))

    def __init__(self, operation_mode_service=None,
                 joystick_device_name="Wireless Controller"):
        self.operation_mode_service = operation_mode_service
        self.joystick_device_name = str(
            joystick_device_name or "Wireless Controller"
        )
        self._stop_event = threading.Event()
        self._thread = None
        self._display = None
        self._background = None
        self._font = None
        self._compact_font = None
        self._display_lock = threading.RLock()

    def start(self):
        """Shows the status screen immediately and starts periodic updates."""
        if self._thread is not None and self._thread.is_alive():
            return

        try:
            from ev3dev2.display import Display  # pylint: disable=import-error

            self._display = Display()
            self._background = self._load_background()
            self._font = self._load_font(8)
            self._compact_font = self._load_font(6)
            self._stop_event.clear()
            self._draw_current_screen()
            self._play_operator_prompt_async()
            self._thread = threading.Thread(
                target=self._run,
                name="Ev3OperationStatusThread"
            )
            self._thread.daemon = True
            self._thread.start()
        except ImportError:
            return
        except (
                IOError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError) as error:
            AppLogger.error(
                "Unable to display EV3 operation-status screen: {0}".format(
                    error
                )
            )

    def stop(self):
        """Stops periodic status updates."""
        self._stop_event.set()
        if (self._thread is not None and
                self._thread is not threading.current_thread()):
            self._thread.join(timeout=2.0)

    def close(self):
        """Provides the lifecycle method expected by RoverApplication."""
        self.stop()

    def _run(self):
        while not self._stop_event.wait(self.REFRESH_SECONDS):
            try:
                self._draw_current_screen()
            except (
                    IOError, OSError, RuntimeError, AttributeError,
                    TypeError, ValueError) as error:
                AppLogger.error(
                    "Unable to update EV3 operation-status screen: {0}".format(
                        error
                    )
                )

    @classmethod
    def _asset_path(cls):
        return screen_asset_path(cls.BACKGROUND_FILENAME)

    @classmethod
    def _load_background(cls):
        return load_monochrome_screen(
            cls._asset_path(),
            "Operation-status screen"
        )

    @staticmethod
    def _load_font(size=8):
        from PIL import ImageFont  # pylint: disable=import-error

        for font_name in (
                "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(font_name, size)
            except IOError:
                continue
        return ImageFont.load_default()

    def _draw_current_screen(self):
        if self._display is None or self._background is None:
            return

        with self._display_lock:
            self._display.image.paste(self._background, (0, 0))
            values = self._read_values()
            for field_name, position in self.VALUE_POSITIONS.items():
                font = (
                    self._compact_font
                    if field_name in self.COMPACT_VALUE_FIELDS
                    else self._font
                )
                self._display.draw.text(
                    position,
                    values[field_name],
                    font=font,
                    fill="black"
                )
            self._display.update()

    def _read_values(self):
        selected_mode = self._read_operation_mode()
        return {
            "battery": self._read_battery_percentage(),
            "ip": self._read_ip_address(),
            "joystick": self._read_joystick_status(),
            "command": self._display_value(
                selected_mode.get("command", "Unavailable")
            ),
            "control": self._display_value(
                selected_mode.get("control") or "N/A"
            )
        }

    def _read_operation_mode(self):
        if self.operation_mode_service is None:
            return {}
        try:
            return self.operation_mode_service.get_mode()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return {}

    @staticmethod
    def _display_value(value):
        text = str(value)
        if text.upper() == "N/A":
            return "N/A"
        return text.capitalize()

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
                device = None
                try:
                    device = evdev.InputDevice(path)
                    if device.name == self.joystick_device_name:
                        return "Connected"
                except (IOError, OSError, RuntimeError, AttributeError):
                    continue
                finally:
                    if device is not None:
                        try:
                            device.close()
                        except (IOError, OSError, RuntimeError, AttributeError):
                            pass
        except (ImportError, IOError, OSError, RuntimeError, AttributeError):
            pass
        return "Disconnected"

    @classmethod
    def _read_battery_percentage(cls):
        try:
            from ev3dev2.power import PowerSupply  # pylint: disable=import-error

            supply = PowerSupply(address=cls.EV3_POWER_SUPPLY_ADDRESS)
            measured = float(supply.measured_volts)
            maximum = float(supply.max_volts)
            if maximum <= 0:
                return "Unavailable"
            percentage = max(
                0,
                min(100, int(round(measured * 100.0 / maximum)))
            )
            return "{0}%".format(percentage)
        except (
                ImportError, IOError, OSError, RuntimeError,
                AttributeError, TypeError, ValueError):
            return "Unavailable"

    @classmethod
    def _play_operator_prompt_async(cls):
        thread = threading.Thread(
            target=cls._play_operator_prompt,
            name="Ev3OperationReadyPromptThread"
        )
        thread.daemon = True
        thread.start()

    @classmethod
    def _play_operator_prompt(cls):
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
            AppLogger.warning(
                "Unable to speak Rover ready announcement: {0}".format(error)
            )
