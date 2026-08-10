#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 adapter for LOCAL Front, Drive and drive-detail selection."""

import time

from app.operation_mode_service import (
    Centrics,
    DifferentialModes,
    Drives,
    Fronts
)
from infrastructure.ev3.button_feedback import Ev3ButtonFeedback
from infrastructure.ev3.framebuffer_display import create_ev3_display
from infrastructure.ev3.screen_image import (
    cached_screen_path,
    load_monochrome_screen
)
from infrastructure.logging.app_logger import AppLogger
from ports.local_drive_setup_selector_port import LocalDriveSetupSelectorPort


class Ev3LocalDriveSetupSelectorAdapter(LocalDriveSetupSelectorPort):
    """Displays one cohesive Front/Drive/Mode setup screen."""

    NAVIGATION_BACK = "BACK"

    BUTTON_POLL_SECONDS = 0.05
    OPERATOR_PROMPT_BEEP_COUNT = 3
    OPERATOR_PROMPT_FREQUENCY_HZ = 1000
    OPERATOR_PROMPT_TONE_MS = 70
    OPERATOR_PROMPT_GAP_SECONDS = 0.04

    OPTION_FRONT = 0
    OPTION_DRIVE = 1
    OPTION_DETAIL = 2
    OPTION_CENTRIC = OPTION_DETAIL
    OPTION_DIFFERENTIAL_MODE = OPTION_DETAIL
    OPTION_CONFIRM = 3
    INITIAL_OPTION_INDEX = OPTION_CONFIRM

    ROW_LEFT_BORDER_X = (14, 14, 14, 14)
    CURSOR_BORDER_GAP = 1
    CURSOR_CENTER_Y = (57, 77, 97, 117)
    CURSOR_HALF_WIDTH = 4
    CURSOR_HALF_HEIGHT = 4

    BACKGROUND_FILENAMES = {
        (Fronts.NOSE, Drives.DIFFERENTIAL, None, DifferentialModes.DUOWHELL):
            "Screen 04 - Front Drive Centric - Nose Differential Duowhell.pbm",
        (Fronts.NOSE, Drives.DIFFERENTIAL, None, DifferentialModes.R_BOGIE):
            "Screen 04 - Front Drive Centric - Nose Differential R-Bogie.pbm",
        (Fronts.TAIL, Drives.DIFFERENTIAL, None, DifferentialModes.DUOWHELL):
            "Screen 04 - Front Drive Centric - Tail Differential Duowhell.pbm",
        (Fronts.TAIL, Drives.DIFFERENTIAL, None, DifferentialModes.R_BOGIE):
            "Screen 04 - Front Drive Centric - Tail Differential R-Bogie.pbm",
        (Fronts.NOSE, Drives.MECANUM, Centrics.CHASSIS, None):
            "Screen 04 - Front Drive Centric - Nose Mecanum Chassis.pbm",
        (Fronts.NOSE, Drives.MECANUM, Centrics.FIELD, None):
            "Screen 04 - Front Drive Centric - Nose Mecanum Field.pbm",
        (Fronts.TAIL, Drives.MECANUM, Centrics.CHASSIS, None):
            "Screen 04 - Front Drive Centric - Tail Mecanum Chassis.pbm",
        (Fronts.TAIL, Drives.MECANUM, Centrics.FIELD, None):
            "Screen 04 - Front Drive Centric - Tail Mecanum Field.pbm"
    }
    BACKGROUND_FILENAME = BACKGROUND_FILENAMES[
        (Fronts.NOSE, Drives.DIFFERENTIAL, None, DifferentialModes.R_BOGIE)
    ]

    def select_setup(self, front, drive, centric, differential_mode=None):
        """Moves among applicable rows until confirmed or cancelled."""
        try:
            from ev3dev2.button import Button  # pylint: disable=import-error
            display = create_ev3_display()
            buttons = Button()
            front, drive, centric, differential_mode = self._normalize_setup(
                front, drive, centric, differential_mode
            )
            backgrounds = self._load_backgrounds()
            option_index = self.INITIAL_OPTION_INDEX

            self._wait_until_released(buttons)
            self._draw(
                display,
                backgrounds[self._background_key(
                    front, drive, centric, differential_mode
                )],
                option_index
            )
            self._play_operator_prompt()

            while True:
                button_name = self._pressed_button(buttons)
                if button_name is None:
                    time.sleep(self.BUTTON_POLL_SECONDS)
                    continue

                (option_index, front, drive, centric,
                 differential_mode, action_performed) = self._handle_button(
                    button_name, option_index,
                    front, drive, centric, differential_mode,
                    display, backgrounds
                )

                if action_performed:
                    Ev3ButtonFeedback.play()

                self._wait_until_released(buttons)

                if self._is_back_navigation(button_name, option_index):
                    return {"navigation": self.NAVIGATION_BACK}

                if (button_name == "enter" and
                        option_index == self.OPTION_CONFIRM):
                    return self._selected_setup(
                        front, drive, centric, differential_mode
                    )

                if button_name == "backspace":
                    return None

        except ImportError:
            front, drive, centric, differential_mode = self._normalize_setup(
                front, drive, centric, differential_mode
            )
            return self._selected_setup(
                front, drive, centric, differential_mode
            )
        except (
                IOError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError) as error:
            message = (
                "Unable to display EV3 Front/Drive/Mode screen: {0}"
                .format(error)
            )
            AppLogger.error(message)
            raise RuntimeError(message)

    @classmethod
    def _handle_button(cls, button_name, option_index,
                       front, drive, centric, differential_mode,
                       display, backgrounds):
        action_performed = False

        if button_name == "up":
            option_index = cls._previous_option(option_index, drive)
            action_performed = True
        elif button_name == "down":
            option_index = cls._next_option(option_index, drive)
            action_performed = True
        elif cls._changes_selected_value(button_name, option_index, drive):
            front, drive, centric, differential_mode = (
                cls._change_selected_setup(
                    option_index, front, drive, centric, differential_mode
                )
            )
            option_index = cls._normalize_option(option_index, drive)
            action_performed = True
        elif cls._is_navigation_action(button_name, option_index):
            action_performed = True

        if action_performed and not cls._is_navigation_action(
                button_name, option_index):
            cls._draw_selected_setup(
                display, backgrounds, option_index,
                front, drive, centric, differential_mode
            )

        return (
            option_index, front, drive, centric,
            differential_mode, action_performed
        )

    @classmethod
    def _draw_selected_setup(cls, display, backgrounds, option_index,
                             front, drive, centric, differential_mode):
        cls._draw(
            display,
            backgrounds[cls._background_key(
                front, drive, centric, differential_mode
            )],
            option_index
        )

    @classmethod
    def _is_navigation_action(cls, button_name, option_index):
        return (
            cls._is_back_navigation(button_name, option_index) or
            cls._is_confirm_selection(button_name, option_index) or
            button_name == "backspace"
        )

    @classmethod
    def _is_confirm_selection(cls, button_name, option_index):
        return (
            button_name == "enter" and
            option_index == cls.OPTION_CONFIRM
        )

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
                "Unable to emit Front/Drive/Mode prompt beeps: {0}".format(
                    error
                )
            )

    @classmethod
    def _asset_path(cls, front=Fronts.NOSE,
                    drive=Drives.DIFFERENTIAL, centric=None,
                    differential_mode=DifferentialModes.R_BOGIE):
        return cached_screen_path(
            cls.BACKGROUND_FILENAMES[
                cls._background_key(
                    front, drive, centric, differential_mode
                )
            ]
        )

    @classmethod
    def _load_background(cls, front=Fronts.NOSE,
                         drive=Drives.DIFFERENTIAL, centric=None,
                         differential_mode=DifferentialModes.R_BOGIE):
        return load_monochrome_screen(
            cls._asset_path(front, drive, centric, differential_mode),
            "Front/Drive/Mode screen"
        )

    @classmethod
    def _load_backgrounds(cls):
        return {
            setup: cls._load_background(*setup)
            for setup in cls.BACKGROUND_FILENAMES
        }

    @staticmethod
    def _normalize_setup(front, drive, centric, differential_mode=None):
        if front not in Fronts.values():
            front = Fronts.NOSE
        if drive not in Drives.values():
            drive = Drives.DIFFERENTIAL
        if centric not in Centrics.values():
            centric = Centrics.CHASSIS
        if differential_mode not in DifferentialModes.values():
            differential_mode = DifferentialModes.R_BOGIE
        return front, drive, centric, differential_mode

    @staticmethod
    def _background_key(front, drive, centric, differential_mode=None):
        if drive == Drives.DIFFERENTIAL:
            active_mode = differential_mode or DifferentialModes.R_BOGIE
            return front, drive, None, active_mode
        return front, drive, centric, None

    @classmethod
    def _active_options(cls, drive):
        del drive
        return (
            cls.OPTION_FRONT,
            cls.OPTION_DRIVE,
            cls.OPTION_DETAIL,
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
        del drive
        value_button = (
            button_name in ("left", "right") or
            button_name == "enter"
        )
        if not value_button or option_index == cls.OPTION_CONFIRM:
            return False
        return option_index in (
            cls.OPTION_FRONT,
            cls.OPTION_DRIVE,
            cls.OPTION_DETAIL
        )

    @classmethod
    def _change_selected_setup(cls, option_index, front, drive, centric,
                               differential_mode=DifferentialModes.R_BOGIE):
        if option_index == cls.OPTION_FRONT:
            front = Fronts.TAIL if front == Fronts.NOSE else Fronts.NOSE
        elif option_index == cls.OPTION_DRIVE:
            drive = (
                Drives.MECANUM
                if drive == Drives.DIFFERENTIAL else Drives.DIFFERENTIAL
            )
        elif option_index == cls.OPTION_DETAIL:
            if drive == Drives.MECANUM:
                centric = (
                    Centrics.FIELD
                    if centric == Centrics.CHASSIS else Centrics.CHASSIS
                )
            else:
                differential_mode = (
                    DifferentialModes.R_BOGIE
                    if differential_mode == DifferentialModes.DUOWHELL
                    else DifferentialModes.DUOWHELL
                )
        return front, drive, centric, differential_mode

    _toggle_selected_setup = _change_selected_setup

    @staticmethod
    def _selected_setup(front, drive, centric, differential_mode):
        return {
            "front": front,
            "drive": drive,
            "centric": centric if drive == Drives.MECANUM else None,
            "differential_mode": (
                differential_mode if drive == Drives.DIFFERENTIAL else None
            )
        }

    @classmethod
    def _is_back_navigation(cls, button_name, option_index):
        return (
            button_name == "left" and option_index == cls.OPTION_CONFIRM
        )

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
