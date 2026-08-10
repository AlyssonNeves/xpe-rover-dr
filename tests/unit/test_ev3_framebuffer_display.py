#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for EV3 32-bit framebuffer byte-order compatibility."""

import unittest

from PIL import Image

from infrastructure.ev3.framebuffer_display import (
    EV3_RAW_PIXEL_MODE,
    create_ev3_display
)


class BitField(object):
    def __init__(self, offset, length):
        self.offset = offset
        self.length = length


class VarInfo(object):
    def __init__(self, bits_per_pixel=32, red_offset=16, green_offset=8,
                 blue_offset=0, transp_length=0):
        self.bits_per_pixel = bits_per_pixel
        self.red = BitField(red_offset, 8)
        self.green = BitField(green_offset, 8)
        self.blue = BitField(blue_offset, 8)
        self.transp = BitField(0, transp_length)


class RecordingDisplay(object):
    def __init__(self, var_info):
        self.var_info = var_info
        self.image = Image.new("L", (1, 1), 255)
        self.mmap = bytearray(4)
        self.update_calls = 0

    def update(self):
        self.update_calls += 1


class Ev3FramebufferDisplayTests(unittest.TestCase):
    def test_ev3_32bit_layout_uses_bgrx_bytes(self):
        native_display = RecordingDisplay(VarInfo())

        display = create_ev3_display(native_display)
        display.update()

        self.assertIs(native_display, display)
        self.assertEqual("BGRX", EV3_RAW_PIXEL_MODE)
        self.assertEqual(b"\xff\xff\xff\x00", bytes(display.mmap))
        self.assertEqual(0, native_display.update_calls)

    def test_non_matching_layout_delegates_to_native_update(self):
        native_display = RecordingDisplay(
            VarInfo(red_offset=0, green_offset=8, blue_offset=16)
        )

        display = create_ev3_display(native_display)
        display.update()

        self.assertEqual(1, native_display.update_calls)

    def test_one_pixel_rgb_values_follow_bgrx_memory_order(self):
        native_display = RecordingDisplay(VarInfo())
        native_display.image = Image.new("RGB", (1, 1), (10, 20, 30))

        display = create_ev3_display(native_display)
        display.update()

        self.assertEqual(bytes((30, 20, 10, 0)), bytes(display.mmap))


if __name__ == "__main__":
    unittest.main()
