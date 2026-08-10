#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for Rover Command and Control selection."""

import os
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from adapters.out_ev3_command_control_selector import (
    Ev3CommandControlSelectorAdapter
)
from app.operation_mode_service import Commands, Controls, OperationModeService


class OperationModeServiceTests(unittest.TestCase):
    """Covers validation, applicability and defensive snapshots."""

    def test_defaults_to_local_manual(self):
        service = OperationModeService()
        self.assertEqual(
            {"command": Commands.LOCAL, "control": Controls.MANUAL},
            service.get_mode()
        )

    def test_select_updates_command_and_control_from_port(self):
        selector = mock.Mock()
        selector.select_mode.return_value = {
            "command": Commands.LOCAL,
            "control": Controls.AUTOMATIC
        }
        service = OperationModeService(
            command_control_selector_port=selector
        )

        selected = service.select_command_control()

        self.assertEqual(Commands.LOCAL, selected["command"])
        self.assertEqual(Controls.AUTOMATIC, selected["control"])
        selector.select_mode.assert_called_once_with(
            Commands.LOCAL, Controls.MANUAL
        )

    def test_remote_makes_control_not_applicable(self):
        selector = mock.Mock()
        selector.select_mode.return_value = {
            "command": Commands.REMOTE,
            "control": Controls.AUTOMATIC
        }
        service = OperationModeService(
            command_control_selector_port=selector
        )

        selected = service.select_command_control()

        self.assertEqual(Commands.REMOTE, selected["command"])
        self.assertIsNone(selected["control"])

    def test_returning_to_local_restores_last_local_control(self):
        service = OperationModeService(control=Controls.AUTOMATIC)
        service.set_command_control(Commands.REMOTE)
        service.set_command_control(Commands.LOCAL)
        self.assertEqual(
            {"command": Commands.LOCAL, "control": Controls.AUTOMATIC},
            service.get_mode()
        )

    def test_select_preserves_mode_when_operator_cancels(self):
        selector = mock.Mock()
        selector.select_mode.return_value = None
        service = OperationModeService(
            command_control_selector_port=selector
        )
        self.assertIsNone(service.select_command_control())
        self.assertEqual(Commands.LOCAL, service.get_mode()["command"])

    def test_rejects_unsupported_values(self):
        with self.assertRaises(ValueError):
            OperationModeService(command="INVALID")
        with self.assertRaises(ValueError):
            OperationModeService(control="INVALID")
        service = OperationModeService()
        with self.assertRaises(ValueError):
            service.set_command_control(Commands.LOCAL, "INVALID")


class Ev3CommandControlSelectorAdapterTests(unittest.TestCase):
    """Covers deterministic Command/Control selector behavior."""

    def test_uses_three_graphical_command_control_screens(self):
        adapter = Ev3CommandControlSelectorAdapter()
        self.assertEqual(3, len(adapter.BACKGROUND_FILENAMES))
        for modes, filename in adapter.BACKGROUND_FILENAMES.items():
            self.assertTrue(filename.startswith("Screen 02 - Command Control"))
            path = adapter._asset_path(*modes)
            self.assertTrue(os.path.isfile(path), path)
            self.assertIn(os.path.join("assets", "screens", "cache"), path)
            background = adapter._load_background(*modes)
            self.assertEqual((178, 128), background.size)
            self.assertEqual("1", background.mode)
            background.close()

    def test_remote_skips_control_row(self):
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

    def test_change_selected_command_and_control(self):
        adapter = Ev3CommandControlSelectorAdapter()
        self.assertEqual(
            (Commands.REMOTE, Controls.MANUAL),
            adapter._change_selected_mode(
                adapter.OPTION_COMMAND, Commands.LOCAL, Controls.MANUAL
            )
        )
        self.assertEqual(
            (Commands.LOCAL, Controls.AUTOMATIC),
            adapter._change_selected_mode(
                adapter.OPTION_CONTROL, Commands.LOCAL, Controls.MANUAL
            )
        )

    def test_falls_back_to_current_modes_without_ev3_api(self):
        adapter = Ev3CommandControlSelectorAdapter()
        with mock.patch.dict("sys.modules", {"ev3dev2.button": None}):
            selected = adapter.select_mode(Commands.LOCAL, Controls.MANUAL)
        self.assertEqual(
            {"command": Commands.LOCAL, "control": Controls.MANUAL},
            selected
        )

    def test_remote_fallback_returns_control_none(self):
        adapter = Ev3CommandControlSelectorAdapter()
        with mock.patch.dict("sys.modules", {"ev3dev2.button": None}):
            selected = adapter.select_mode(Commands.REMOTE, Controls.MANUAL)
        self.assertEqual(
            {"command": Commands.REMOTE, "control": None}, selected
        )

    def test_button_feedback_is_best_effort(self):
        feedback = mock.Mock()
        adapter = Ev3CommandControlSelectorAdapter(button_feedback=feedback)
        adapter._play_button_feedback()
        feedback.play.assert_called_once_with()

    def test_draw_adds_cursor_to_selected_row(self):
        from PIL import Image, ImageDraw

        class FakeDisplay(object):
            def __init__(self):
                self.image = Image.new("1", (178, 128), 1)
                self.draw = ImageDraw.Draw(self.image)
                self.update_count = 0

            def update(self):
                self.update_count += 1

        adapter = Ev3CommandControlSelectorAdapter()
        background = Image.new("1", (178, 128), 1)
        display = FakeDisplay()
        adapter._draw(display, background, adapter.OPTION_COMMAND)
        self.assertEqual(0, display.image.getpixel((5, 57)))
        self.assertEqual(1, display.update_count)
        background.close()
        display.image.close()


if __name__ == "__main__":
    unittest.main()
