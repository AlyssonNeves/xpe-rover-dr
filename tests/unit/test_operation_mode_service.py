#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for Rover operating-mode selection."""

import os
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from adapters.out_ev3_operation_mode_selector import (
    Ev3OperationModeSelectorAdapter
)
from app.operation_mode_service import (
    CommandModes,
    OperationModes,
    OperationModeService
)


class OperationModeServiceTests(unittest.TestCase):
    """Covers validation, selection and defensive snapshots."""

    def test_defaults_to_local_manual(self):
        service = OperationModeService()
        self.assertEqual(
            {
                "command_mode": CommandModes.LOCAL,
                "operation_mode": OperationModes.MANUAL
            },
            service.get_mode()
        )

    def test_select_updates_modes_from_port(self):
        selector = mock.Mock()
        selector.select_mode.return_value = {
            "command_mode": CommandModes.REMOTE,
            "operation_mode": OperationModes.AUTOMATIC
        }
        service = OperationModeService(selector_port=selector)

        selected = service.select()

        self.assertEqual(CommandModes.REMOTE, selected["command_mode"])
        self.assertEqual(OperationModes.AUTOMATIC, selected["operation_mode"])
        selector.select_mode.assert_called_once_with(
            CommandModes.LOCAL,
            OperationModes.MANUAL
        )

    def test_select_preserves_mode_when_operator_cancels(self):
        selector = mock.Mock()
        selector.select_mode.return_value = None
        service = OperationModeService(selector_port=selector)
        self.assertIsNone(service.select())
        self.assertEqual(CommandModes.LOCAL, service.get_mode()["command_mode"])

    def test_rejects_unsupported_values(self):
        with self.assertRaises(ValueError):
            OperationModeService(command_mode="INVALID")
        with self.assertRaises(ValueError):
            OperationModeService(operation_mode="INVALID")


class Ev3OperationModeSelectorAdapterTests(unittest.TestCase):
    """Covers deterministic selector helper behavior."""

    def test_toggle_command_mode(self):
        adapter = Ev3OperationModeSelectorAdapter()
        self.assertEqual(
            CommandModes.REMOTE,
            adapter._toggle_command_mode(CommandModes.LOCAL)
        )
        self.assertEqual(
            CommandModes.LOCAL,
            adapter._toggle_command_mode(CommandModes.REMOTE)
        )

    def test_toggle_operation_mode(self):
        adapter = Ev3OperationModeSelectorAdapter()
        self.assertEqual(
            OperationModes.AUTOMATIC,
            adapter._toggle_operation_mode(OperationModes.MANUAL)
        )
        self.assertEqual(
            OperationModes.MANUAL,
            adapter._toggle_operation_mode(OperationModes.AUTOMATIC)
        )

    def test_falls_back_to_current_mode_without_ev3_api(self):
        adapter = Ev3OperationModeSelectorAdapter()
        with mock.patch.dict("sys.modules", {"ev3dev2.button": None}):
            selected = adapter.select_mode(
                CommandModes.LOCAL,
                OperationModes.MANUAL
            )
        self.assertEqual(CommandModes.LOCAL, selected["command_mode"])
        self.assertEqual(OperationModes.MANUAL, selected["operation_mode"])

    def test_uses_three_graphical_command_control_screens(self):
        adapter = Ev3OperationModeSelectorAdapter()
        self.assertEqual(3, len(adapter.BACKGROUND_FILENAMES))

        for modes, filename in adapter.BACKGROUND_FILENAMES.items():
            self.assertTrue(filename.startswith("Screen 02 - Command Control"))
            path = adapter._asset_path(*modes)
            self.assertTrue(os.path.isfile(path), path)
            background = adapter._load_background(*modes)
            self.assertEqual((178, 128), background.size)
            self.assertEqual("1", background.mode)
            background.close()

    def test_remote_screen_does_not_depend_on_operation_value(self):
        adapter = Ev3OperationModeSelectorAdapter()
        self.assertEqual(
            (CommandModes.REMOTE, None),
            adapter._background_key(
                CommandModes.REMOTE,
                OperationModes.AUTOMATIC
            )
        )

    def test_draw_pastes_selected_graphical_background(self):
        from PIL import Image

        class FakeDisplay(object):
            def __init__(self):
                self.image = Image.new("1", (178, 128), 1)
                self.update_count = 0

            def update(self):
                self.update_count += 1

        adapter = Ev3OperationModeSelectorAdapter()
        background = Image.new("1", (178, 128), 0)
        backgrounds = {
            (CommandModes.LOCAL, OperationModes.MANUAL): background
        }
        display = FakeDisplay()

        adapter._draw(
            display,
            backgrounds,
            CommandModes.LOCAL,
            OperationModes.MANUAL
        )

        self.assertEqual(0, display.image.getpixel((20, 20)))
        self.assertEqual(1, display.update_count)
        background.close()
        display.image.close()


if __name__ == "__main__":
    unittest.main()
