#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 adapter for LOCAL Front, Drive and Centric selection."""

import time

from app.operation_mode_service import Centrics, Drives, Fronts
from infrastructure.ev3.button_feedback import Ev3ButtonFeedback
from infrastructure.ev3.screen_image import (
    cached_screen_path,
    load_monochrome_screen
)
from infrastructure.logging.app_logger import AppLogger
from ports.local_drive_setup_selector_port import LocalDriveSetupSelectorPort


class Ev3LocalDriveSetupSelectorAdapter(LocalDriveSetupSelectorPort):
    """Displays one cohesive Front/Drive/Centric setup screen."""

    BUTTON_POLL_SECONDS = 0.05
    OPERATOR_PROMPT_BEEP_COUNT = 3
    OPERATOR_PROMPT_FREQUENCY_HZ = 1000
    OPERATOR_PROMPT_TONE_MS = 70
    OPERATOR_PROMPT_GAP_SECONDS = 0.04

    OPTION_FRONT = 0
    OPTION_DRIVE = 1
    OPTION_CENTRIC = 2
    OPTION_CONFIRM = 3
    INITIAL_OPTION_INDEX = OPTION_CONFIRM

    ROW_LEFT_BORDER_X = (14, 14, 14, 14)
    CURSOR_BORDER_GAP = 1
    CURSOR_CENTER_Y = (57, 77, 97, 117)
    CURSOR_HALF_WIDTH = 4
    CURSOR_HALF_HEIGHT = 4

    BACKGROUND_FILENAMES = {
        (Fronts.NOSE, Drives.DIFFERENTIAL, None):
            "Screen 04 - Front Drive Centric - Nose Differential.pbm",
        (Fronts.TAIL, Drives.DIFFERENTIAL, None):
            "Screen 04 - Front Drive Centric - Tail Differential.pbm",
        (Fronts.NOSE, Drives.MECANUM, Centrics.CHASSIS):
            "Screen 04 - Front Drive Centric - Nose Mecanum Chassis.pbm",
        (Fronts.NOSE, Drives.MECANUM, Centrics.FIELD):
            "Screen 04 - Front Drive Centric - Nose Mecanum Field.pbm",
        (Fronts.TAIL, Drives.MECANUM, Centrics.CHASSIS):
            "Screen 04 - Front Drive Centric - Tail Mecanum Chassis.pbm",
        (Fronts.TAIL, Drives.MECANUM, Centrics.FIELD):
            "Screen 04 - Front Drive Centric - Tail Mecanum Field.pbm"
    }
    BACKGROUND_FILENAME = BACKGROUND_FILENAMES[
        (Fronts.NOSE, Drives.DIFFERENTIAL, None)
    ]

    def select_setup(self, front, drive, centric):
        """Moves among applicable rows until confirmed or cancelled."""
        try:
            from ev3dev2.button import Button  # pylint: disable=import-error
            from ev3dev2.display import Display  # pylint: disable=import-error

            display = Display()
            buttons = Button()
            front, drive, centric = self._normalize_setup(
                front, drive, centric
            )
            backgrounds = self._load_backgrounds()
            option_index = self.INITIAL_OPTION_INDEX

            self._wait_until_released(buttons)
            self._draw(
                display,
                backgrounds[self._background_key(front, drive, centric)],
                option_index
            )
            self._play_operator_prompt()

            while True:
                button_name = self._pressed_button(buttons)
                if button_name is None:
                    time.sleep(self.BUTTON_POLL_SECONDS)
                    continue

                Ev3ButtonFeedback.play()

                if button_name == "up":
                    option_index = self._previous_option(option_index, drive)
                    self._draw(
                        display,
                        backgrounds[self._background_key(front, drive, centric)],
                        option_index
                    )

                elif button_name == "down":
                    option_index = self._next_option(option_index, drive)
                    self._draw(
                        display,
                        backgrounds[self._background_key(front, drive, centric)],
                        option_index
                    )

                elif self._changes_selected_value(
                        button_name, option_index, drive):
                    front, drive, centric = self._change_selected_setup(
                        option_index, front, drive, centric
                    )
                    option_index = self._normalize_option(option_index, drive)
                    self._draw(
                        display,
                        backgrounds[self._background_key(front, drive, centric)],
                        option_index
                    )

                self._wait_until_released(buttons)

                if (button_name == "enter" and
                        option_index == self.OPTION_CONFIRM):
                    return {
                        "front": front,
                        "drive": drive,
                        "centric": (
                            centric if drive == Drives.MECANUM else None
                        )
                    }

                if button_name == "backspace":
                    return None

        except ImportError:
            front, drive, centric = self._normalize_setup(
                front, drive, centric
            )
            return {
                "front": front,
                "drive": drive,
                "centric": centric if drive == Drives.MECANUM else None
            }
        except (
                IOError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError) as error:
            message = (
                "Unable to display EV3 Front/Drive/Centric screen: {0}"
                .format(error)
            )
            AppLogger.error(message)
            raise RuntimeError(message)

    @classmethod
    def _play_operator_prompt(cls):
        try:
            from ev3dev2.sound import Sound  # pylint: disable=import-error

            sound = Sound()
            for beep_index in range(cls.OPERATOR_PROMPT_BEEP_COUNT):
                sound.tone(
                    cls.OPERATOR_PROMPT_FREQUENCY_HZ,
                    cls.OPERATOR_PROMPT_TONE_MS,
                    play_type=Sound.PLAY_WAIT_FOR_COMPLETE
                )
                if beep_index < cls.OPERATOR_PROMPT_BEEP_COUNT - 1:
                    time.sleep(cls.OPERATOR_PROMPT_GAP_SECONDS)
        except (
                ImportError, IOError, OSError, RuntimeError,
                AttributeError, TypeError) as error:
            AppLogger.warning(
                "Unable to emit Front/Drive/Centric prompt beeps: {0}".format(
                    error
                )
            )

    @classmethod
    def _asset_path(cls, front=Fronts.NOSE,
                    drive=Drives.DIFFERENTIAL, centric=None):
        return cached_screen_path(
            cls.BACKGROUND_FILENAMES[
                cls._background_key(front, drive, centric)
            ]
        )

    @classmethod
    def _load_background(cls, front=Fronts.NOSE,
                         drive=Drives.DIFFERENTIAL, centric=None):
        return load_monochrome_screen(
            cls._asset_path(front, drive, centric),
            "Front/Drive/Centric screen"
        )

    @classmethod
    def _load_backgrounds(cls):
        return {
            setup: cls._load_background(*setup)
            for setup in cls.BACKGROUND_FILENAMES
        }

    @staticmethod
    def _normalize_setup(front, drive, centric):
        if front not in Fronts.values():
            front = Fronts.NOSE
        if drive not in Drives.values():
            drive = Drives.DIFFERENTIAL
        if centric not in Centrics.values():
            centric = Centrics.CHASSIS
        return front, drive, centric

    @staticmethod
    def _background_key(front, drive, centric):
        if drive == Drives.DIFFERENTIAL:
            return front, drive, None
        return front, drive, centric

    @classmethod
    def _active_options(cls, drive):
        if drive == Drives.DIFFERENTIAL:
            return (cls.OPTION_FRONT, cls.OPTION_DRIVE, cls.OPTION_CONFIRM)
        return (
            cls.OPTION_FRONT,
            cls.OPTION_DRIVE,
            cls.OPTION_CENTRIC,
            cls.OPTION_CONFIRM
        )

    @classmethod
    def _normalize_option(cls, option_index, drive):
        active = cls._active_options(drive)
        return option_index if option_index in active else cls.OPTION_DRIVE

    @classmethod
    def _previous_option(cls, option_index,
                         drive=Drives.DIFFERENTIAL):
        active = cls._active_options(drive)
        current = cls._normalize_option(option_index, drive)
        return active[(active.index(current) - 1) % len(active)]

    @classmethod
    def _next_option(cls, option_index,
                     drive=Drives.DIFFERENTIAL):
        active = cls._active_options(drive)
        current = cls._normalize_option(option_index, drive)
        return active[(active.index(current) + 1) % len(active)]

    @classmethod
    def _changes_selected_value(cls, button_name, option_index,
                                drive=Drives.DIFFERENTIAL):
        value_button = (
            button_name in ("left", "right") or
            button_name == "enter"
        )
        if not value_button or option_index == cls.OPTION_CONFIRM:
            return False
        if option_index == cls.OPTION_CENTRIC:
            return drive == Drives.MECANUM
        return option_index in (cls.OPTION_FRONT, cls.OPTION_DRIVE)

    @classmethod
    def _change_selected_setup(cls, option_index, front, drive, centric):
        if option_index == cls.OPTION_FRONT:
            front = Fronts.TAIL if front == Fronts.NOSE else Fronts.NOSE
        elif option_index == cls.OPTION_DRIVE:
            drive = (
                Drives.MECANUM
                if drive == Drives.DIFFERENTIAL else Drives.DIFFERENTIAL
            )
        elif option_index == cls.OPTION_CENTRIC and drive == Drives.MECANUM:
            centric = (
                Centrics.FIELD
                if centric == Centrics.CHASSIS else Centrics.CHASSIS
            )
        return front, drive, centric

    _toggle_selected_setup = _change_selected_setup

    @classmethod
    def _draw(cls, display, background, option_index):
        display.image.paste(background, (0, 0))
        cursor_tip_x = (
            cls.ROW_LEFT_BORDER_X[option_index] - cls.CURSOR_BORDER_GAP
        )
        center_x = cursor_tip_x - cls.CURSOR_HALF_WIDTH
        center_y = cls.CURSOR_CENTER_Y[option_index]
        display.draw.polygon(
            (
                (center_x - cls.CURSOR_HALF_WIDTH,
                 center_y - cls.CURSOR_HALF_HEIGHT),
                (center_x - cls.CURSOR_HALF_WIDTH,
                 center_y + cls.CURSOR_HALF_HEIGHT),
                (center_x + cls.CURSOR_HALF_WIDTH, center_y)
            ),
            fill=0
        )
        display.update()

    @classmethod
    def _pressed_button(cls, buttons):
        for name in ("up", "down", "left", "right", "enter", "backspace"):
            if cls._is_pressed(buttons, name):
                return name
        return None

    @classmethod
    def _wait_until_released(cls, buttons):
        while cls._any_pressed(buttons):
            time.sleep(cls.BUTTON_POLL_SECONDS)

    @staticmethod
    def _any_pressed(buttons):
        try:
            return bool(buttons.any())
        except (OSError, RuntimeError, AttributeError):
            return any(
                Ev3LocalDriveSetupSelectorAdapter._is_pressed(buttons, name)
                for name in (
                    "enter", "backspace", "up", "down", "left", "right"
                )
            )

    @staticmethod
    def _is_pressed(buttons, name):
        try:
            return bool(getattr(buttons, name))
        except (OSError, RuntimeError, AttributeError):
            return False
