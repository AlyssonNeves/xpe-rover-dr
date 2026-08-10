#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for direct loading and in-memory reuse of EV3 PBM screens."""

import os
import shutil
import tempfile
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from PIL import Image

from infrastructure.ev3 import screen_image
from infrastructure.ev3.screen_image import (
    EV3_SCREEN_SIZE,
    clear_monochrome_screen_memory_cache,
    default_screen_cache_path,
    load_monochrome_screen,
    warm_monochrome_screen_cache
)


class Ev3ScreenImageTestCase(unittest.TestCase):
    """Covers ready-made PBM validation, loading and memory reuse."""

    def setUp(self):
        clear_monochrome_screen_memory_cache()
        self.temp_directory = tempfile.mkdtemp()

    def tearDown(self):
        clear_monochrome_screen_memory_cache()
        shutil.rmtree(self.temp_directory)

    def _asset_path(self, filename="Test screen.pbm", value=1,
                    size=EV3_SCREEN_SIZE):
        asset_path = os.path.join(self.temp_directory, filename)
        source = Image.new("1", size, value)
        source.save(asset_path, format="PPM")
        source.close()
        return asset_path

    def test_ready_pbm_is_loaded_without_conversion(self):
        asset_path = self._asset_path(value=0)
        loaded = load_monochrome_screen(asset_path, "Test screen")

        self.assertEqual("1", loaded.mode)
        self.assertEqual(EV3_SCREEN_SIZE, loaded.size)
        self.assertEqual(0, loaded.getpixel((20, 20)))
        loaded.close()

    def test_non_monochrome_asset_is_rejected_instead_of_converted(self):
        asset_path = os.path.join(self.temp_directory, "Invalid mode.pbm")
        source = Image.new("L", EV3_SCREEN_SIZE, 128)
        source.save(asset_path, format="PPM")
        source.close()

        with self.assertRaisesRegex(
                ValueError,
                "must be a 1-bit monochrome PBM image"):
            load_monochrome_screen(asset_path, "Test screen")

    def test_invalid_screen_size_is_rejected(self):
        asset_path = self._asset_path(size=(100, 100))

        with self.assertRaisesRegex(
                ValueError,
                "Test screen must be 178x128 pixels"):
            load_monochrome_screen(asset_path, "Test screen")

    def test_same_process_load_uses_memory_cache(self):
        asset_path = self._asset_path()
        first = load_monochrome_screen(asset_path, "Test screen")
        first.close()

        with mock.patch.object(
                screen_image,
                "_open_valid_pbm",
                wraps=screen_image._open_valid_pbm) as open_mock:
            second = load_monochrome_screen(asset_path, "Test screen")

        self.assertEqual("1", second.mode)
        self.assertEqual(0, open_mock.call_count)
        second.close()

    def test_changed_pbm_invalidates_memory_entry(self):
        asset_path = self._asset_path(value=1)
        first = load_monochrome_screen(asset_path, "Test screen")
        first.close()

        replacement = Image.new("1", EV3_SCREEN_SIZE, 0)
        replacement.save(asset_path, format="PPM")
        replacement.close()
        os.utime(asset_path, None)

        with mock.patch.object(
                screen_image,
                "_open_valid_pbm",
                wraps=screen_image._open_valid_pbm) as open_mock:
            second = load_monochrome_screen(asset_path, "Test screen")

        self.assertEqual(1, open_mock.call_count)
        self.assertEqual(0, second.getpixel((20, 20)))
        second.close()

    def test_warm_cache_loads_all_existing_pbm_files(self):
        self._asset_path("First.pbm", 1)
        self._asset_path("Second.PBM", 0)
        with open(os.path.join(self.temp_directory, "Ignored.txt"), "w") as item:
            item.write("not a screen")

        first_result = warm_monochrome_screen_cache(self.temp_directory)
        second_result = warm_monochrome_screen_cache(self.temp_directory)

        self.assertEqual(2, first_result["total"])
        self.assertEqual(2, first_result["loaded"])
        self.assertEqual(0, first_result["memory_hits"])
        self.assertEqual([], first_result["failed"])
        self.assertEqual(2, second_result["memory_hits"])
        self.assertEqual(0, second_result["loaded"])

    def test_warm_cache_reports_invalid_pbm_without_converting_it(self):
        self._asset_path("Valid.pbm")
        invalid_path = os.path.join(self.temp_directory, "Invalid.pbm")
        with open(invalid_path, "wb") as invalid_file:
            invalid_file.write(b"not-a-pbm")

        result = warm_monochrome_screen_cache(self.temp_directory)

        self.assertEqual(2, result["total"])
        self.assertEqual(1, result["loaded"])
        self.assertEqual(1, len(result["failed"]))
        self.assertEqual("Invalid.pbm", result["failed"][0][0])

    def test_packaged_cache_contains_only_valid_ev3_pbm_screens(self):
        cache_path = default_screen_cache_path()
        filenames = sorted(
            filename for filename in os.listdir(cache_path)
            if filename.lower().endswith(".pbm")
        )

        self.assertEqual(17, len(filenames))
        for filename in filenames:
            background = load_monochrome_screen(
                os.path.join(cache_path, filename),
                filename
            )
            self.assertEqual(EV3_SCREEN_SIZE, background.size)
            self.assertEqual("1", background.mode)
            background.close()

    def test_runtime_screen_directory_has_no_tiff_sources_or_manifest(self):
        screens_path = os.path.dirname(default_screen_cache_path())
        screen_files = os.listdir(screens_path)
        cache_files = os.listdir(default_screen_cache_path())

        self.assertFalse(any(
            filename.lower().endswith((".tif", ".tiff"))
            for filename in screen_files
        ))
        self.assertNotIn("screen_cache_manifest.json", cache_files)


if __name__ == "__main__":
    unittest.main()
