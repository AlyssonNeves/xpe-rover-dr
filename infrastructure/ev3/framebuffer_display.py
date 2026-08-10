#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Creates EV3 displays with the correct 32-bit framebuffer byte layout."""


EV3_FRAMEBUFFER_BITS_PER_PIXEL = 32
EV3_RED_OFFSET = 16
EV3_GREEN_OFFSET = 8
EV3_BLUE_OFFSET = 0
EV3_CHANNEL_LENGTH = 8
EV3_TRANSPARENCY_LENGTH = 0
EV3_RAW_PIXEL_MODE = "BGRX"


def create_ev3_display(native_display=None):
    """Returns a Display whose updates match the EV3 32-bit framebuffer."""
    if native_display is None:
        from ev3dev2.display import Display  # pylint: disable=import-error

        native_display = Display()

    if _uses_ev3_bgrx32_layout(native_display):
        native_display.update = _bgrx32_update_for(native_display)

    return native_display


def _bgrx32_update_for(display):
    """Builds an update callable bound to one native ev3dev2 display."""
    def update():
        framebuffer_bytes = (
            display.image.convert("RGB").tobytes(
                "raw",
                EV3_RAW_PIXEL_MODE
            )
        )
        display.mmap[:] = framebuffer_bytes

    return update


def _uses_ev3_bgrx32_layout(display):
    """Checks the channel offsets reported by the active framebuffer."""
    var_info = getattr(display, "var_info", None)
    if var_info is None:
        return False

    red = getattr(var_info, "red", None)
    green = getattr(var_info, "green", None)
    blue = getattr(var_info, "blue", None)
    transp = getattr(var_info, "transp", None)
    if red is None or green is None or blue is None or transp is None:
        return False

    return (
        getattr(var_info, "bits_per_pixel", None) ==
        EV3_FRAMEBUFFER_BITS_PER_PIXEL and
        getattr(red, "offset", None) == EV3_RED_OFFSET and
        getattr(red, "length", None) == EV3_CHANNEL_LENGTH and
        getattr(green, "offset", None) == EV3_GREEN_OFFSET and
        getattr(green, "length", None) == EV3_CHANNEL_LENGTH and
        getattr(blue, "offset", None) == EV3_BLUE_OFFSET and
        getattr(blue, "length", None) == EV3_CHANNEL_LENGTH and
        getattr(transp, "length", None) == EV3_TRANSPARENCY_LENGTH
    )
