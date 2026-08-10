#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import unittest

from adapters.out_ev3_local_drive_setup_selector import (
    Ev3LocalDriveSetupSelectorAdapter,
)
from app.operation_mode_service import Centrics, Drives, Fronts


class Ev3LocalDriveSetupSelectorTests(unittest.TestCase):
    def test_uses_six_packaged_front_drive_centric_screens(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertEqual(6, len(adapter.BACKGROUND_FILENAMES))
        for setup, filename in adapter.BACKGROUND_FILENAMES.items():
            self.assertTrue(filename.startswith("Screen 04 - Front Drive Centric"))
            path = adapter._asset_path(*setup)
            self.assertTrue(os.path.isfile(path), path)
            background = adapter._load_background(*setup)
            self.assertEqual((178, 128), background.size)
            self.assertEqual("1", background.mode)
            background.close()

    def test_differential_skips_centric_row(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertEqual(
            (adapter.OPTION_FRONT, adapter.OPTION_DRIVE, adapter.OPTION_CONFIRM),
            adapter._active_options(Drives.DIFFERENTIAL),
        )
        self.assertFalse(adapter._changes_selected_value(
            "enter", adapter.OPTION_CENTRIC, Drives.DIFFERENTIAL
        ))

    def test_mecanum_enables_centric_and_toggles_field(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertIn(adapter.OPTION_CENTRIC, adapter._active_options(Drives.MECANUM))
        changed = adapter._change_selected_setup(
            adapter.OPTION_CENTRIC,
            Fronts.NOSE,
            Drives.MECANUM,
            Centrics.CHASSIS,
        )
        self.assertEqual((Fronts.NOSE, Drives.MECANUM, Centrics.FIELD), changed)

    def test_differential_background_ignores_centric(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertEqual(
            (Fronts.TAIL, Drives.DIFFERENTIAL, None),
            adapter._background_key(Fronts.TAIL, Drives.DIFFERENTIAL, Centrics.FIELD),
        )


if __name__ == "__main__":
    unittest.main()
