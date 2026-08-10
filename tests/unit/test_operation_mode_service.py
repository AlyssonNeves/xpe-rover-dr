#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the canonical Rover operation-mode service."""

import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from app.operation_mode_service import (
    Centrics,
    Commands,
    Controls,
    Drives,
    Fronts,
    OperationModeService,
    RoverOperationMode,
    coerce_operation_mode,
)


class RoverOperationModeTests(unittest.TestCase):
    def test_default_snapshot_contains_all_parameters(self):
        self.assertEqual({
            "command": Commands.LOCAL,
            "control": Controls.MANUAL,
            "front": Fronts.NOSE,
            "drive": Drives.DIFFERENTIAL,
            "centric": None,
        }, RoverOperationMode().to_dict())

    def test_remote_makes_local_parameters_not_applicable(self):
        mode = RoverOperationMode(
            command=Commands.REMOTE,
            control=Controls.AUTOMATIC,
            front=Fronts.TAIL,
            drive=Drives.MECANUM,
            centric=Centrics.FIELD,
        )
        self.assertEqual({
            "command": Commands.REMOTE,
            "control": None,
            "front": None,
            "drive": None,
            "centric": None,
        }, mode.to_dict())

    def test_differential_makes_centric_not_applicable(self):
        self.assertIsNone(
            RoverOperationMode(
                drive=Drives.DIFFERENTIAL,
                centric=Centrics.FIELD,
            ).centric
        )

    def test_mecanum_defaults_to_chassis(self):
        self.assertEqual(
            Centrics.CHASSIS,
            RoverOperationMode(drive=Drives.MECANUM).centric,
        )

    def test_rejects_invalid_values(self):
        invalid = (
            {"command": "NETWORK"},
            {"control": "ASSISTED"},
            {"front": "LEFT"},
            {"drive": "TRACKED"},
            {"drive": Drives.MECANUM, "centric": "MAP"},
        )
        for values in invalid:
            with self.assertRaises(ValueError):
                RoverOperationMode(**values)

    def test_coerce_accepts_canonical_dictionary_and_rejects_legacy_fields(self):
        mode = coerce_operation_mode({
            "command": Commands.LOCAL,
            "control": Controls.MANUAL,
            "front": Fronts.TAIL,
            "drive": Drives.MECANUM,
            "centric": Centrics.CHASSIS,
        })
        self.assertEqual(Fronts.TAIL, mode.front)
        self.assertEqual(Drives.MECANUM, mode.drive)
        with self.assertRaises(ValueError):
            coerce_operation_mode({"drive_system": "MECANUM"})


class OperationModeServiceTests(unittest.TestCase):
    def test_command_control_selection_updates_one_snapshot(self):
        selector = mock.Mock()
        selector.select_mode.return_value = {
            "command": Commands.REMOTE,
            "control": None,
        }
        service = OperationModeService(command_control_selector_port=selector)
        selected = service.select_command_control()
        self.assertEqual(Commands.REMOTE, selected["command"])
        self.assertIsNone(selected["control"])
        self.assertIsNone(selected["front"])
        self.assertIsNone(selected["drive"])
        self.assertIsNone(selected["centric"])

    def test_local_drive_selection_updates_front_drive_and_centric_together(self):
        selector = mock.Mock()
        selector.select_setup.return_value = {
            "front": Fronts.TAIL,
            "drive": Drives.MECANUM,
            "centric": Centrics.FIELD,
        }
        service = OperationModeService(local_drive_selector_port=selector)
        selected = service.select_local_drive()
        selector.select_setup.assert_called_once_with(
            Fronts.NOSE, Drives.DIFFERENTIAL, Centrics.CHASSIS
        )
        self.assertEqual(Fronts.TAIL, selected["front"])
        self.assertEqual(Drives.MECANUM, selected["drive"])
        self.assertEqual(Centrics.FIELD, selected["centric"])

    def test_local_values_are_retained_while_remote(self):
        service = OperationModeService(
            control=Controls.AUTOMATIC,
            front=Fronts.TAIL,
            drive=Drives.MECANUM,
            centric=Centrics.CHASSIS,
        )
        service.set_command_control(Commands.REMOTE)
        self.assertIsNone(service.get_snapshot()["front"])
        service.set_command_control(Commands.LOCAL)
        self.assertEqual(Controls.AUTOMATIC, service.get_snapshot()["control"])
        self.assertEqual(Fronts.TAIL, service.get_snapshot()["front"])
        self.assertEqual(Drives.MECANUM, service.get_snapshot()["drive"])

    def test_remote_rejects_local_drive_selection(self):
        service = OperationModeService(command=Commands.REMOTE)
        with self.assertRaises(RuntimeError):
            service.select_local_drive()

    def test_cancellation_preserves_mode(self):
        selector = mock.Mock()
        selector.select_mode.return_value = None
        service = OperationModeService(command_control_selector_port=selector)
        before = service.get_snapshot()
        self.assertIsNone(service.select_command_control())
        self.assertEqual(before, service.get_snapshot())

    def test_mode_object_exposes_local_manual_predicate(self):
        service = OperationModeService()
        self.assertTrue(service.get_mode().is_local_manual())
        service.set_command_control(Commands.LOCAL, Controls.AUTOMATIC)
        self.assertFalse(service.get_mode().is_local_manual())


if __name__ == "__main__":
    unittest.main()
