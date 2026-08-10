#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the first graphical EV3 PBM screen loader."""

import os
import shutil
import tempfile
import unittest

from PIL import Image

from infrastructure.ev3.screen_image import (
    EV3_SCREEN_SIZE,
    load_monochrome_screen,
    screen_asset_path,
    screen_assets_path
)


class Ev3ScreenImageTests(unittest.TestCase):
    """Covers direct loading and validation of EV3 PBM assets."""

    def setUp(self):
        self.temp_directory = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_directory)

    def _image_path(self, mode="1", size=EV3_SCREEN_SIZE):
        path = os.path.join(self.temp_directory, "screen.pbm")
        image = Image.new(mode, size, 1)
        image.save(path, format="PPM")
        image.close()
        return path

    def test_screen_assets_path_points_to_project_assets(self):
        self.assertTrue(screen_assets_path().endswith("assets/screens"))
        self.assertEqual(
            os.path.join(screen_assets_path(), "sample.pbm"),
            screen_asset_path("sample.pbm")
        )

    def test_loads_ready_monochrome_ev3_screen(self):
        loaded = load_monochrome_screen(self._image_path(), "Test screen")
        self.assertEqual("1", loaded.mode)
        self.assertEqual((178, 128), loaded.size)
        loaded.close()

    def test_rejects_non_monochrome_screen(self):
        with self.assertRaisesRegex(ValueError, "1-bit monochrome"):
            load_monochrome_screen(
                self._image_path(mode="L"),
                "Test screen"
            )

    def test_rejects_wrong_screen_dimensions(self):
        with self.assertRaisesRegex(ValueError, "178x128"):
            load_monochrome_screen(
                self._image_path(size=(100, 100)),
                "Test screen"
            )


if __name__ == "__main__":
    unittest.main()
