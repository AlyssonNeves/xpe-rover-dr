#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the new Command/Control and Front/Drive/Centric EV3 screens."""

import os
import sys
import types
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from adapters.out_ev3_command_control_selector import (
    Ev3CommandControlSelectorAdapter
)
from adapters.out_ev3_local_drive_setup_selector import (
    Ev3LocalDriveSetupSelectorAdapter
)
from app.operation_mode_service import (
    Centrics, Commands, Controls, DifferentialModes, Drives, Fronts
)




class _DummyButton(object):
    up = False
    down = False
    left = False
    right = False
    enter = False
    backspace = False

    def any(self):
        return False


class _DummyDisplay(object):
    def __init__(self):
        self.image = mock.Mock()
        self.draw = mock.Mock()

    def update(self):
        return None

class Ev3CommandControlSelectorTests(unittest.TestCase):
    def test_uses_three_group_named_screen_assets(self):
        adapter = Ev3CommandControlSelectorAdapter()
        self.assertEqual(3, len(adapter.BACKGROUND_FILENAMES))
        for modes, filename in adapter.BACKGROUND_FILENAMES.items():
            self.assertTrue(filename.startswith("Screen 02 - Command Control"))
            path = adapter._asset_path(*modes)
            self.assertTrue(os.path.isfile(path), path)
            background = adapter._load_background(*modes)
            self.assertEqual((178, 128), background.size)
            self.assertEqual("1", background.mode)


    def test_confirm_row_right_does_not_beep_or_change_anything(self):
        adapter = Ev3CommandControlSelectorAdapter()
        fake_module = types.SimpleNamespace(Button=_DummyButton)
        with mock.patch.dict(sys.modules, {"ev3dev2.button": fake_module}):
            with mock.patch(
                    "adapters.out_ev3_command_control_selector.create_ev3_display",
                    return_value=_DummyDisplay()):
                with mock.patch.object(
                        Ev3CommandControlSelectorAdapter,
                        "_load_backgrounds",
                        return_value={
                            (Commands.LOCAL, Controls.MANUAL): object(),
                            (Commands.LOCAL, Controls.AUTOMATIC): object(),
                            (Commands.REMOTE, None): object()
                        }):
                    with mock.patch.object(
                            Ev3CommandControlSelectorAdapter,
                            "_draw") as draw_mock:
                        with mock.patch.object(
                                Ev3CommandControlSelectorAdapter,
                                "_play_operator_prompt"):
                            with mock.patch.object(
                                    Ev3CommandControlSelectorAdapter,
                                    "_wait_until_released"):
                                with mock.patch.object(
                                        Ev3CommandControlSelectorAdapter,
                                        "_pressed_button",
                                        side_effect=["right", "backspace"]):
                                    with mock.patch(
                                            "adapters.out_ev3_command_control_selector.Ev3ButtonFeedback.play") as beep_mock:
                                        selected = adapter.select_mode(
                                            Commands.LOCAL, Controls.MANUAL
                                        )

        self.assertIsNone(selected)
        self.assertEqual(1, beep_mock.call_count)
        self.assertEqual(1, draw_mock.call_count)

    def test_remote_skips_the_inapplicable_control_row(self):
        adapter = Ev3CommandControlSelectorAdapter()
        self.assertEqual(
            (adapter.OPTION_COMMAND, adapter.OPTION_CONFIRM),
            adapter._active_options(Commands.REMOTE)
        )
        self.assertEqual(
            adapter.OPTION_CONFIRM,
            adapter._next_option(adapter.OPTION_COMMAND, Commands.REMOTE)
        )
        self.assertFalse(
            adapter._changes_selected_value(
                "enter", adapter.OPTION_CONTROL, Commands.REMOTE
            )
        )

    def test_local_allows_manual_and_automatic_control(self):
        adapter = Ev3CommandControlSelectorAdapter()
        self.assertEqual(
            (Commands.LOCAL, Controls.AUTOMATIC),
            adapter._change_selected_mode(
                adapter.OPTION_CONTROL,
                Commands.LOCAL,
                Controls.MANUAL
            )
        )


class Ev3LocalDriveSetupSelectorTests(unittest.TestCase):


    def test_confirm_row_enter_beeps_then_returns_without_extra_prompt(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        fake_module = types.SimpleNamespace(Button=_DummyButton)
        events = []
        with mock.patch.dict(sys.modules, {"ev3dev2.button": fake_module}):
            with mock.patch(
                    "adapters.out_ev3_local_drive_setup_selector.create_ev3_display",
                    return_value=_DummyDisplay()):
                with mock.patch.object(
                        Ev3LocalDriveSetupSelectorAdapter,
                        "_load_backgrounds",
                        return_value={
                            (Fronts.NOSE, Drives.DIFFERENTIAL, None,
                             DifferentialModes.R_BOGIE): object()
                        }):
                    with mock.patch.object(
                            Ev3LocalDriveSetupSelectorAdapter,
                            "_background_key",
                            return_value=(
                                Fronts.NOSE, Drives.DIFFERENTIAL, None,
                                DifferentialModes.R_BOGIE
                            )):
                        with mock.patch.object(
                                Ev3LocalDriveSetupSelectorAdapter,
                                "_draw"):
                            with mock.patch.object(
                                    Ev3LocalDriveSetupSelectorAdapter,
                                    "_play_operator_prompt",
                                    side_effect=lambda: events.append("prompt")):
                                with mock.patch.object(
                                        Ev3LocalDriveSetupSelectorAdapter,
                                        "_wait_until_released",
                                        side_effect=lambda _buttons: events.append("wait")):
                                    with mock.patch.object(
                                            Ev3LocalDriveSetupSelectorAdapter,
                                            "_pressed_button",
                                            return_value="enter"):
                                        with mock.patch(
                                                "adapters.out_ev3_local_drive_setup_selector.Ev3ButtonFeedback.play",
                                                side_effect=lambda: events.append("beep")):
                                            selected = adapter.select_setup(
                                                Fronts.NOSE,
                                                Drives.DIFFERENTIAL,
                                                None,
                                                DifferentialModes.R_BOGIE
                                            )

        self.assertEqual(Fronts.NOSE, selected["front"])
        self.assertEqual(Drives.DIFFERENTIAL, selected["drive"])
        self.assertEqual(
            DifferentialModes.R_BOGIE,
            selected["differential_mode"]
        )
        self.assertEqual(
            ["wait", "prompt", "beep", "wait"],
            events
        )

    def test_confirm_row_right_is_silent_and_left_beeps_and_goes_back(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        fake_module = types.SimpleNamespace(Button=_DummyButton)
        with mock.patch.dict(sys.modules, {"ev3dev2.button": fake_module}):
            with mock.patch(
                    "adapters.out_ev3_local_drive_setup_selector.create_ev3_display",
                    return_value=_DummyDisplay()):
                with mock.patch.object(
                        Ev3LocalDriveSetupSelectorAdapter,
                        "_load_backgrounds",
                        return_value={
                            (Fronts.NOSE, Drives.DIFFERENTIAL, None,
                             DifferentialModes.R_BOGIE): object()
                        }):
                    with mock.patch.object(
                            Ev3LocalDriveSetupSelectorAdapter,
                            "_background_key",
                            return_value=(
                                Fronts.NOSE, Drives.DIFFERENTIAL, None,
                                DifferentialModes.R_BOGIE
                            )):
                        with mock.patch.object(
                                Ev3LocalDriveSetupSelectorAdapter,
                                "_draw") as draw_mock:
                            with mock.patch.object(
                                    Ev3LocalDriveSetupSelectorAdapter,
                                    "_play_operator_prompt"):
                                with mock.patch.object(
                                        Ev3LocalDriveSetupSelectorAdapter,
                                        "_wait_until_released"):
                                    with mock.patch.object(
                                            Ev3LocalDriveSetupSelectorAdapter,
                                            "_pressed_button",
                                            side_effect=["right", "left"]):
                                        with mock.patch(
                                                "adapters.out_ev3_local_drive_setup_selector.Ev3ButtonFeedback.play") as beep_mock:
                                            selected = adapter.select_setup(
                                                Fronts.NOSE,
                                                Drives.DIFFERENTIAL,
                                                None,
                                                DifferentialModes.R_BOGIE
                                            )

        self.assertEqual({"navigation": "BACK"}, selected)
        self.assertEqual(1, beep_mock.call_count)
        self.assertEqual(1, draw_mock.call_count)

    def test_uses_eight_group_named_screen_assets(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertEqual(8, len(adapter.BACKGROUND_FILENAMES))
        for setup, filename in adapter.BACKGROUND_FILENAMES.items():
            self.assertTrue(
                filename.startswith("Screen 04 - Front Drive Centric")
            )
            path = adapter._asset_path(*setup)
            self.assertTrue(os.path.isfile(path), path)
            background = adapter._load_background(*setup)
            self.assertEqual((178, 128), background.size)
            self.assertEqual("1", background.mode)

    def test_differential_defaults_to_r_bogie(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        normalized = adapter._normalize_setup(
            Fronts.NOSE, Drives.DIFFERENTIAL, None, None
        )
        self.assertEqual(DifferentialModes.R_BOGIE, normalized[3])
        self.assertEqual(
            (
                Fronts.NOSE, Drives.DIFFERENTIAL, None,
                DifferentialModes.R_BOGIE
            ),
            adapter._background_key(
                Fronts.NOSE, Drives.DIFFERENTIAL, None, None
            )
        )

    def test_differential_uses_detail_row_for_mechanical_mode(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertEqual(
            (
                adapter.OPTION_FRONT,
                adapter.OPTION_DRIVE,
                adapter.OPTION_DIFFERENTIAL_MODE,
                adapter.OPTION_CONFIRM
            ),
            adapter._active_options(Drives.DIFFERENTIAL)
        )
        changed = adapter._change_selected_setup(
            adapter.OPTION_DIFFERENTIAL_MODE,
            Fronts.NOSE,
            Drives.DIFFERENTIAL,
            Centrics.CHASSIS,
            DifferentialModes.DUOWHELL
        )
        self.assertEqual(
            (
                Fronts.NOSE, Drives.DIFFERENTIAL, Centrics.CHASSIS,
                DifferentialModes.R_BOGIE
            ),
            changed
        )

    def test_mecanum_uses_detail_row_for_centric_mode(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertIn(
            adapter.OPTION_CENTRIC,
            adapter._active_options(Drives.MECANUM)
        )
        changed = adapter._change_selected_setup(
            adapter.OPTION_CENTRIC,
            Fronts.NOSE,
            Drives.MECANUM,
            Centrics.CHASSIS,
            DifferentialModes.DUOWHELL
        )
        self.assertEqual(
            (
                Fronts.NOSE, Drives.MECANUM, Centrics.FIELD,
                DifferentialModes.DUOWHELL
            ),
            changed
        )


    def test_confirm_row_left_requests_navigation_back(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertTrue(
            adapter._is_back_navigation(
                "left", adapter.OPTION_CONFIRM
            )
        )
        self.assertFalse(
            adapter._is_back_navigation(
                "right", adapter.OPTION_CONFIRM
            )
        )
        self.assertFalse(
            adapter._is_back_navigation(
                "left", adapter.OPTION_FRONT
            )
        )

    def test_differential_background_key_uses_mechanical_mode(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertEqual(
            (
                Fronts.TAIL, Drives.DIFFERENTIAL, None,
                DifferentialModes.R_BOGIE
            ),
            adapter._background_key(
                Fronts.TAIL, Drives.DIFFERENTIAL, Centrics.FIELD,
                DifferentialModes.R_BOGIE
            )
        )

    def test_mecanum_background_key_ignores_differential_mode(self):
        adapter = Ev3LocalDriveSetupSelectorAdapter()
        self.assertEqual(
            (Fronts.NOSE, Drives.MECANUM, Centrics.FIELD, None),
            adapter._background_key(
                Fronts.NOSE, Drives.MECANUM, Centrics.FIELD,
                DifferentialModes.R_BOGIE
            )
        )


if __name__ == "__main__":
    unittest.main()
