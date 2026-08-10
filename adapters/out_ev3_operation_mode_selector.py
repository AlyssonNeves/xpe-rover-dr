#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 adapter that presents graphical Rover operating-mode screens."""

import os
import time

from adapters.ev3_button_feedback import Ev3ButtonFeedback
from adapters.ev3_screen_image import (
    load_monochrome_screen,
    screen_asset_path
)
from app.operation_mode_service import CommandModes, OperationModes
from ports.operation_mode_selector_port import OperationModeSelectorPort


class Ev3OperationModeSelectorAdapter(OperationModeSelectorPort):
    """Displays PBM mode screens and reads the EV3 brick buttons."""

    SCREEN_WIDTH = 178
    SCREEN_HEIGHT = 128
    BUTTON_POLL_SECONDS = 0.05

    REGULAR_FONT_PATHS = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
    )
    BOLD_FONT_PATHS = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
    )

    def __init__(self, button_feedback=None):
        self.button_feedback = button_feedback or Ev3ButtonFeedback

    BACKGROUND_FILENAMES = {
        (CommandModes.LOCAL, OperationModes.MANUAL):
            "Screen 02 - Command Control - Local Manual.pbm",
        (CommandModes.LOCAL, OperationModes.AUTOMATIC):
            "Screen 02 - Command Control - Local Automatic.pbm",
        (CommandModes.REMOTE, None):
            "Screen 02 - Command Control - Remote.pbm"
    }

    def select_mode(self, command_mode, operation_mode):
        """Waits until the operator changes and confirms the desired mode."""
        try:
            from ev3dev2.button import Button  # pylint: disable=import-error
            from ev3dev2.display import Display  # pylint: disable=import-error

            display = Display()
            buttons = Button()
            backgrounds = self._load_backgrounds()

            self._wait_until_released(buttons)
            self._draw(display, backgrounds, command_mode, operation_mode)

            while True:
                if self._is_pressed(buttons, "left"):
                    self._play_button_feedback()
                    command_mode = self._toggle_command_mode(command_mode)
                    self._draw(
                        display,
                        backgrounds,
                        command_mode,
                        operation_mode
                    )
                    self._wait_until_released(buttons)

                elif self._is_pressed(buttons, "right"):
                    self._play_button_feedback()
                    operation_mode = self._toggle_operation_mode(operation_mode)
                    self._draw(
                        display,
                        backgrounds,
                        command_mode,
                        operation_mode
                    )
                    self._wait_until_released(buttons)

                elif self._is_pressed(buttons, "enter"):
                    self._play_button_feedback()
                    self._draw_confirmation(
                        display,
                        command_mode,
                        operation_mode
                    )
                    self._wait_until_released(buttons)
                    return {
                        "command_mode": command_mode,
                        "operation_mode": operation_mode
                    }

                elif self._is_pressed(buttons, "backspace"):
                    self._play_button_feedback()
                    self._wait_until_released(buttons)
                    return None

                time.sleep(self.BUTTON_POLL_SECONDS)

        except (
                ImportError, OSError, RuntimeError, AttributeError,
                TypeError, ValueError):
            return {
                "command_mode": command_mode,
                "operation_mode": operation_mode
            }

    @classmethod
    def _background_key(cls, command_mode, operation_mode):
        if command_mode == CommandModes.REMOTE:
            return CommandModes.REMOTE, None
        return command_mode, operation_mode

    @classmethod
    def _asset_path(cls, command_mode, operation_mode):
        key = cls._background_key(command_mode, operation_mode)
        return screen_asset_path(cls.BACKGROUND_FILENAMES[key])

    @classmethod
    def _load_background(cls, command_mode, operation_mode):
        return load_monochrome_screen(
            cls._asset_path(command_mode, operation_mode),
            "Command/Control screen"
        )

    @classmethod
    def _load_backgrounds(cls):
        return {
            key: cls._load_background(*key)
            for key in cls.BACKGROUND_FILENAMES
        }

    @classmethod
    def _draw(cls, display, backgrounds, command_mode, operation_mode):
        key = cls._background_key(command_mode, operation_mode)
        display.image.paste(backgrounds[key], (0, 0))
        display.update()

    @classmethod
    def _draw_confirmation(cls, display, command_mode, operation_mode):
        from PIL import ImageFont  # pylint: disable=import-error

        draw = display.draw
        font_title = cls._load_font(ImageFont, cls.BOLD_FONT_PATHS, 14)
        font_text = cls._load_font(ImageFont, cls.REGULAR_FONT_PATHS, 11)

        draw.rectangle(
            (0, 0, cls.SCREEN_WIDTH - 1, cls.SCREEN_HEIGHT - 1),
            fill="white"
        )
        draw.rectangle((0, 0, cls.SCREEN_WIDTH - 1, 22), fill="black")
        draw.text((43, 4), "EV3 ROBOT", font=font_title, fill="white")
        draw.text((23, 37), "MODO SELECIONADO", font=font_text, fill="black")
        draw.text((28, 61), command_mode, font=font_title, fill="black")
        draw.text((28, 82), operation_mode, font=font_title, fill="black")
        draw.text((45, 108), "INICIANDO...", font=font_text, fill="black")
        display.update()

    @staticmethod
    def _load_font(image_font, paths, size):
        for path in paths:
            if os.path.exists(path):
                try:
                    return image_font.truetype(path, size)
                except (IOError, OSError):
                    continue
        return image_font.load_default()

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
                Ev3OperationModeSelectorAdapter._is_pressed(buttons, name)
                for name in (
                    "left", "right", "enter", "backspace", "up", "down"
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

    @staticmethod
    def _toggle_command_mode(command_mode):
        if command_mode == CommandModes.LOCAL:
            return CommandModes.REMOTE
        return CommandModes.LOCAL

    @staticmethod
    def _toggle_operation_mode(operation_mode):
        if operation_mode == OperationModes.MANUAL:
            return OperationModes.AUTOMATIC
        return OperationModes.MANUAL
