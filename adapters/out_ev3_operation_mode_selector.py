#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 adapter that presents the Rover operating-mode selection screen."""

import os
import time

from app.operation_mode_service import CommandModes, OperationModes
from ports.operation_mode_selector_port import OperationModeSelectorPort


class Ev3OperationModeSelectorAdapter(OperationModeSelectorPort):
    """Draws the selector on the EV3 LCD and reads the brick buttons."""

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

    def select_mode(self, command_mode, operation_mode):
        """Waits until the operator changes and confirms the desired mode."""
        try:
            from ev3dev2.button import Button  # pylint: disable=import-error
            from ev3dev2.display import Display  # pylint: disable=import-error

            display = Display()
            buttons = Button()

            self._wait_until_released(buttons)
            self._draw(display, command_mode, operation_mode)

            while True:
                if self._is_pressed(buttons, "left"):
                    command_mode = self._toggle_command_mode(command_mode)
                    self._draw(display, command_mode, operation_mode)
                    self._wait_until_released(buttons)

                elif self._is_pressed(buttons, "right"):
                    operation_mode = self._toggle_operation_mode(operation_mode)
                    self._draw(display, command_mode, operation_mode)
                    self._wait_until_released(buttons)

                elif self._is_pressed(buttons, "enter"):
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
                    self._wait_until_released(buttons)
                    return None

                time.sleep(self.BUTTON_POLL_SECONDS)

        except (ImportError, OSError, RuntimeError, AttributeError, TypeError):
            return {
                "command_mode": command_mode,
                "operation_mode": operation_mode
            }

    @classmethod
    def _draw(cls, display, command_mode, operation_mode):
        from PIL import ImageFont  # pylint: disable=import-error

        image = display.image
        draw = display.draw
        draw.rectangle((0, 0, cls.SCREEN_WIDTH - 1, cls.SCREEN_HEIGHT - 1), fill="white")

        font_small = cls._load_font(ImageFont, cls.REGULAR_FONT_PATHS, 9)
        font_small_bold = cls._load_font(ImageFont, cls.BOLD_FONT_PATHS, 9)
        font_title = cls._load_font(ImageFont, cls.BOLD_FONT_PATHS, 13)
        font_option = cls._load_font(ImageFont, cls.BOLD_FONT_PATHS, 10)

        # Header inspired by the EV3 status bar in the requested reference.
        draw.text((4, 1), "EV3", font=font_title, fill="black")
        draw.rectangle((68, 2, 108, 17), outline="black")
        draw.text((77, 3), "123", font=font_small_bold, fill="black")
        draw.rectangle((151, 4, 173, 15), outline="black")
        draw.rectangle((154, 7, 169, 12), fill="black")
        draw.line((0, 20, 177, 20), fill="black")

        # Rover icon and application title.
        cls._draw_rover_icon(draw, 8, 26)
        draw.line((63, 30, 172, 30), fill="black")
        draw.text((72, 35), "EV3 ROBOT", font=font_title, fill="black")
        draw.line((63, 53, 172, 53), fill="black")

        # Mode groups.
        draw.text((5, 61), "COMANDO", font=font_small_bold, fill="black")
        draw.text((96, 61), "OPERAÇÃO", font=font_small_bold, fill="black")
        draw.line((88, 60, 88, 105), fill="black")

        cls._draw_option(
            draw, 4, 74, 80, 14, "LOCAL",
            command_mode == CommandModes.LOCAL,
            font_option
        )
        cls._draw_option(
            draw, 4, 91, 80, 14, "REMOTO",
            command_mode == CommandModes.REMOTE,
            font_option
        )
        cls._draw_option(
            draw, 94, 74, 80, 14, "MANUAL",
            operation_mode == OperationModes.MANUAL,
            font_option
        )
        cls._draw_option(
            draw, 94, 91, 80, 14, "AUTOMÁTICA",
            operation_mode == OperationModes.AUTOMATIC,
            font_option
        )

        draw.line((4, 109, 173, 109), fill="black")
        draw.text((7, 114), "< COMANDO", font=font_small, fill="black")
        draw.text((67, 114), "> OPERAÇÃO", font=font_small, fill="black")
        draw.text((137, 114), "OK", font=font_small_bold, fill="black")

        display.update()
        del image

    @classmethod
    def _draw_confirmation(cls, display, command_mode, operation_mode):
        from PIL import ImageFont  # pylint: disable=import-error

        draw = display.draw
        font_title = cls._load_font(ImageFont, cls.BOLD_FONT_PATHS, 14)
        font_text = cls._load_font(ImageFont, cls.REGULAR_FONT_PATHS, 11)

        draw.rectangle((0, 0, cls.SCREEN_WIDTH - 1, cls.SCREEN_HEIGHT - 1), fill="white")
        draw.rectangle((0, 0, cls.SCREEN_WIDTH - 1, 22), fill="black")
        draw.text((43, 4), "EV3 ROBOT", font=font_title, fill="white")
        draw.text((23, 37), "MODO SELECIONADO", font=font_text, fill="black")
        draw.text((28, 61), command_mode, font=font_title, fill="black")
        draw.text((28, 82), operation_mode, font=font_title, fill="black")
        draw.text((45, 108), "INICIANDO...", font=font_text, fill="black")
        display.update()

    @staticmethod
    def _draw_option(draw, x_pos, y_pos, width, height, label, selected, font):
        fill = "black" if selected else "white"
        text_fill = "white" if selected else "black"
        draw.rectangle(
            (x_pos, y_pos, x_pos + width, y_pos + height),
            outline="black",
            fill=fill
        )
        center_y = y_pos + (height // 2)
        draw.ellipse(
            (x_pos + 4, center_y - 4, x_pos + 12, center_y + 4),
            outline=text_fill
        )
        if selected:
            draw.ellipse(
                (x_pos + 6, center_y - 2, x_pos + 10, center_y + 2),
                fill=text_fill
            )
        draw.text((x_pos + 17, y_pos + 2), label, font=font, fill=text_fill)

    @staticmethod
    def _draw_rover_icon(draw, x_pos, y_pos):
        draw.ellipse((x_pos + 15, y_pos, x_pos + 45, y_pos + 12), outline="black")
        draw.ellipse((x_pos + 21, y_pos + 3, x_pos + 27, y_pos + 9), fill="black")
        draw.ellipse((x_pos + 34, y_pos + 3, x_pos + 40, y_pos + 9), fill="black")
        draw.rectangle((x_pos + 18, y_pos + 14, x_pos + 43, y_pos + 42), outline="black")
        draw.rectangle((x_pos + 23, y_pos + 19, x_pos + 38, y_pos + 28), outline="black")
        draw.rectangle((x_pos + 11, y_pos + 20, x_pos + 17, y_pos + 41), fill="black")
        draw.rectangle((x_pos + 44, y_pos + 20, x_pos + 50, y_pos + 41), fill="black")
        draw.line((x_pos + 30, y_pos + 28, x_pos + 30, y_pos + 38), fill="black")
        draw.line((x_pos + 26, y_pos + 34, x_pos + 34, y_pos + 34), fill="black")

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
                for name in ("left", "right", "enter", "backspace", "up", "down")
            )

    @staticmethod
    def _is_pressed(buttons, name):
        try:
            return bool(getattr(buttons, name))
        except (OSError, RuntimeError, AttributeError):
            return False

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
