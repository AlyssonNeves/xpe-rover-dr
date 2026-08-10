#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 adapter for Rover Command and Control selection."""

import time

from app.operation_mode_service import Commands, Controls
from infrastructure.ev3.button_feedback import Ev3ButtonFeedback
from infrastructure.ev3.framebuffer_display import create_ev3_display
from infrastructure.ev3.screen_image import (
    cached_screen_path,
    load_monochrome_screen
)
from infrastructure.logging.app_logger import AppLogger
from ports.command_control_selector_port import CommandControlSelectorPort


class Ev3CommandControlSelectorAdapter(CommandControlSelectorPort):
    """Displays Command/Control screens and reads EV3 brick buttons."""

    BUTTON_POLL_SECONDS = 0.05
    OPERATOR_PROMPT_BEEP_COUNT = 3
    OPERATOR_PROMPT_FREQUENCY_HZ = 1000
    OPERATOR_PROMPT_TONE_MS = 70
    OPERATOR_PROMPT_GAP_SECONDS = 0.04

    OPTION_COMMAND = 0
    OPTION_CONTROL = 1
    OPTION_CONFIRM = 2
    INITIAL_OPTION_INDEX = OPTION_CONFIRM

    ROW_LEFT_BORDER_X = (14, 14, 54)
    CURSOR_BORDER_GAP = 1
    CURSOR_CENTER_Y = (57, 77, 117)
    CURSOR_HALF_WIDTH = 4
    CURSOR_HALF_HEIGHT = 4

    BACKGROUND_FILENAMES = {
        (Commands.LOCAL, Controls.MANUAL):
            "Screen 02 - Command Control - Local Manual.pbm",
        (Commands.LOCAL, Controls.AUTOMATIC):
            "Screen 02 - Command Control - Local Automatic.pbm",
        (Commands.REMOTE, None):
            "Screen 02 - Command Control - Remote.pbm"
    }
    BACKGROUND_FILENAME = BACKGROUND_FILENAMES[
        (Commands.LOCAL, Controls.MANUAL)
    ]

    def select_mode(self, command, control):
        """Moves among active rows until the operator confirms or cancels."""
        try:
            from ev3dev2.button import Button  # pylint: disable=import-error
            display = create_ev3_display()
            buttons = Button()
            command, control = self._normalize_modes(command, control)
            backgrounds = self._load_backgrounds()
            option_index = self.INITIAL_OPTION_INDEX

            self._wait_until_released(buttons)
            self._draw(
                display,
                backgrounds[self._background_key(command, control)],
                option_index
            )
            self._play_operator_prompt()

            while True:
                button_name = self._pressed_button(buttons)
                if button_name is None:
                    time.sleep(self.BUTTON_POLL_SECONDS)
                    continue

                (option_index, command, control,
                 action_performed) = self._handle_button(
                    button_name, option_index, command, control,
                    display, backgrounds
                )

                if action_performed:
                    Ev3ButtonFeedback.play()

                self._wait_until_released(buttons)

                if (button_name == "enter" and
                        option_index == self.OPTION_CONFIRM):
                    return {
                        "command": command,
                        "control": (
                            control if command == Commands.LOCAL else None
                        )
                    }

                if button_name == "backspace":
                    return None

        except ImportError:
            command, control = self._normalize_modes(command, control)
            return {
                "command": command,
                "control": control if command == Commands.LOCAL else None
            }
        except (
                IOError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError) as error:
            message = (
                "Unable to display EV3 Command/Control screen: {0}"
                .format(error)
            )
            AppLogger.error(message)
            raise RuntimeError(message)

    @classmethod
    def _handle_button(cls, button_name, option_index, command, control,
                       display, backgrounds):
        action_performed = False
        redraw = False

        if button_name == "up":
            option_index = cls._previous_option(option_index, command)
            action_performed = True
            redraw = True
        elif button_name == "down":
            option_index = cls._next_option(option_index, command)
            action_performed = True
            redraw = True
        elif cls._changes_selected_value(button_name, option_index, command):
            command, control = cls._change_selected_mode(
                option_index, command, control
            )
            option_index = cls._normalize_option(option_index, command)
            action_performed = True
            redraw = True
        elif (button_name == "enter" and
              option_index == cls.OPTION_CONFIRM):
            action_performed = True
        elif button_name == "backspace":
            action_performed = True

        if redraw:
            cls._draw(
                display,
                backgrounds[cls._background_key(command, control)],
                option_index
            )

        return option_index, command, control, action_performed

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
                "Unable to emit Command/Control prompt beeps: {0}".format(
                    error
                )
            )

    @classmethod
    def _asset_path(cls, command=Commands.LOCAL,
                    control=Controls.MANUAL):
        return cached_screen_path(
            cls.BACKGROUND_FILENAMES[cls._background_key(command, control)]
        )

    @classmethod
    def _load_background(cls, command=Commands.LOCAL,
                         control=Controls.MANUAL):
        return load_monochrome_screen(
            cls._asset_path(command, control),
            "Command/Control screen"
        )

    @classmethod
    def _load_backgrounds(cls):
        return {
            modes: cls._load_background(*modes)
            for modes in cls.BACKGROUND_FILENAMES
        }

    @staticmethod
    def _normalize_modes(command, control):
        if command not in Commands.values():
            command = Commands.LOCAL
        if control not in Controls.values():
            control = Controls.MANUAL
        return command, control

    @staticmethod
    def _background_key(command, control):
        if command == Commands.REMOTE:
            return Commands.REMOTE, None
        return command, control

    @classmethod
    def _active_options(cls, command):
        if command == Commands.REMOTE:
            return (cls.OPTION_COMMAND, cls.OPTION_CONFIRM)
        return (cls.OPTION_COMMAND, cls.OPTION_CONTROL, cls.OPTION_CONFIRM)

    @classmethod
    def _normalize_option(cls, option_index, command):
        active = cls._active_options(command)
        return option_index if option_index in active else cls.OPTION_COMMAND

    @classmethod
    def _previous_option(cls, option_index, command=Commands.LOCAL):
        active = cls._active_options(command)
        current = cls._normalize_option(option_index, command)
        return active[(active.index(current) - 1) % len(active)]

    @classmethod
    def _next_option(cls, option_index, command=Commands.LOCAL):
        active = cls._active_options(command)
        current = cls._normalize_option(option_index, command)
        return active[(active.index(current) + 1) % len(active)]

    @classmethod
    def _changes_selected_value(cls, button_name, option_index,
                                command=Commands.LOCAL):
        value_button = (
            button_name in ("left", "right") or
            button_name == "enter"
        )
        if not value_button or option_index == cls.OPTION_CONFIRM:
            return False
        if option_index == cls.OPTION_CONTROL:
            return command == Commands.LOCAL
        return option_index == cls.OPTION_COMMAND

    @classmethod
    def _change_selected_mode(cls, option_index, command, control):
        if option_index == cls.OPTION_COMMAND:
            command = (
                Commands.REMOTE
                if command == Commands.LOCAL else Commands.LOCAL
            )
        elif (option_index == cls.OPTION_CONTROL and
              command == Commands.LOCAL):
            control = (
                Controls.AUTOMATIC
                if control == Controls.MANUAL else Controls.MANUAL
            )
        return command, control

    _toggle_selected_mode = _change_selected_mode

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
                Ev3CommandControlSelectorAdapter._is_pressed(buttons, name)
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
