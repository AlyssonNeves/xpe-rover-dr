#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 adapter for Rover Command and Control selection."""

import time

from adapters.ev3_button_feedback import Ev3ButtonFeedback
from adapters.ev3_screen_image import (
    load_monochrome_screen,
    screen_asset_path
)
from app.operation_mode_service import Commands, Controls
from ports.command_control_selector_port import CommandControlSelectorPort


class Ev3CommandControlSelectorAdapter(CommandControlSelectorPort):
    """Displays Command/Control screens and reads EV3 brick buttons."""

    BUTTON_POLL_SECONDS = 0.05

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

    def __init__(self, button_feedback=None):
        self.button_feedback = button_feedback or Ev3ButtonFeedback

    def select_mode(self, command, control):
        """Moves among active rows until the operator confirms or cancels."""
        try:
            from ev3dev2.button import Button  # pylint: disable=import-error
            from ev3dev2.display import Display  # pylint: disable=import-error

            display = Display()
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

            while True:
                button_name = self._pressed_button(buttons)
                if button_name is None:
                    time.sleep(self.BUTTON_POLL_SECONDS)
                    continue

                self._play_button_feedback()

                if button_name == "up":
                    option_index = self._previous_option(option_index, command)
                elif button_name == "down":
                    option_index = self._next_option(option_index, command)
                elif self._changes_selected_value(
                        button_name, option_index, command):
                    command, control = self._change_selected_mode(
                        option_index, command, control
                    )
                    option_index = self._normalize_option(option_index, command)

                self._draw(
                    display,
                    backgrounds[self._background_key(command, control)],
                    option_index
                )
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

        except (
                ImportError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError):
            command, control = self._normalize_modes(command, control)
            return {
                "command": command,
                "control": control if command == Commands.LOCAL else None
            }

    @classmethod
    def _asset_path(cls, command=Commands.LOCAL, control=Controls.MANUAL):
        return screen_asset_path(
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
        if button_name not in ("left", "right", "enter"):
            return False
        if option_index == cls.OPTION_CONFIRM:
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

    def _play_button_feedback(self):
        """Emits best-effort feedback for one processed brick-button press."""
        try:
            self.button_feedback.play()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
