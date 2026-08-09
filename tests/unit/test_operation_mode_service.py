#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for Rover operating-mode selection."""

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


if __name__ == "__main__":
    unittest.main()
