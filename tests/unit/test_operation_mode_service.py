#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the cohesive Rover operation-mode value and service."""

import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from app.operation_mode_service import (
    Centrics,
    Commands,
    Controls,
    DifferentialModes,
    Drives,
    Fronts,
    OperationModeService,
    RoverOperationMode,
    coerce_operation_mode
)


class RoverOperationModeTests(unittest.TestCase):
    """Covers applicability rules encoded in the canonical value object."""

    def test_default_snapshot_contains_all_parameters(self):
        self.assertEqual(
            {
                "command": Commands.LOCAL,
                "control": Controls.MANUAL,
                "front": Fronts.NOSE,
                "drive": Drives.DIFFERENTIAL,
                "centric": None,
                "differential_mode": DifferentialModes.R_BOGIE
            },
            RoverOperationMode().to_dict()
        )

    def test_remote_makes_all_dependent_parameters_not_applicable(self):
        mode = RoverOperationMode(
            command=Commands.REMOTE,
            control=Controls.AUTOMATIC,
            front=Fronts.TAIL,
            drive=Drives.MECANUM,
            centric=Centrics.FIELD
        )
        self.assertEqual(
            {
                "command": Commands.REMOTE,
                "control": None,
                "front": None,
                "drive": None,
                "centric": None,
                "differential_mode": None
            },
            mode.to_dict()
        )

    def test_differential_makes_centric_not_applicable(self):
        mode = RoverOperationMode(
            drive=Drives.DIFFERENTIAL,
            centric=Centrics.FIELD
        )
        self.assertIsNone(mode.centric)
        self.assertEqual(
            DifferentialModes.R_BOGIE, mode.differential_mode
        )

    def test_differential_accepts_r_bogie_mode(self):
        mode = RoverOperationMode(
            drive=Drives.DIFFERENTIAL,
            differential_mode=DifferentialModes.R_BOGIE
        )
        self.assertEqual(
            DifferentialModes.R_BOGIE, mode.differential_mode
        )

    def test_mecanum_defaults_to_chassis_reference(self):
        mode = RoverOperationMode(drive=Drives.MECANUM)
        self.assertEqual(Centrics.CHASSIS, mode.centric)
        self.assertIsNone(mode.differential_mode)

    def test_rejects_unsupported_parameter_values(self):
        invalid_values = (
            {"command": "NETWORK"},
            {"control": "ASSISTED"},
            {"front": "LEFT"},
            {"drive": "TRACKED"},
            {"drive": Drives.MECANUM, "centric": "MAP"},
            {"differential_mode": "TRACK"}
        )
        for values in invalid_values:
            with self.assertRaises(ValueError):
                RoverOperationMode(**values)

    def test_rejects_removed_legacy_field_names(self):
        with self.assertRaises(ValueError):
            coerce_operation_mode({
                "command_mode": "LOCAL",
                "control_mode": "MANUAL",
                "drive_direction": "REVERSE",
                "drive_system": "MECANUM",
                "mecanum_centric": "ROBOT"
            })

    def test_accepts_canonical_dictionary(self):
        mode = coerce_operation_mode({
            "command": Commands.LOCAL,
            "control": Controls.MANUAL,
            "front": Fronts.TAIL,
            "drive": Drives.MECANUM,
            "centric": Centrics.CHASSIS
        })
        self.assertEqual(Fronts.TAIL, mode.front)
        self.assertEqual(Drives.MECANUM, mode.drive)
        self.assertEqual(Centrics.CHASSIS, mode.centric)


class OperationModeServiceTests(unittest.TestCase):
    """Covers selection through ports and one shared runtime snapshot."""

    def test_command_control_selection_updates_one_structure(self):
        selector = mock.Mock()
        selector.select_mode.return_value = {
            "command": Commands.REMOTE,
            "control": None
        }
        service = OperationModeService(
            command_control_selector_port=selector
        )

        selected = service.select_command_control()

        selector.select_mode.assert_called_once_with(
            Commands.LOCAL, Controls.MANUAL
        )
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
            "centric": Centrics.FIELD
        }
        service = OperationModeService(local_drive_selector_port=selector)

        selected = service.select_local_drive()

        selector.select_setup.assert_called_once_with(
            Fronts.NOSE, Drives.DIFFERENTIAL, Centrics.CHASSIS,
            DifferentialModes.R_BOGIE
        )
        self.assertEqual(Fronts.TAIL, selected["front"])
        self.assertEqual(Drives.MECANUM, selected["drive"])
        self.assertEqual(Centrics.FIELD, selected["centric"])

    def test_local_values_are_retained_but_hidden_while_remote(self):
        service = OperationModeService(
            front=Fronts.TAIL,
            drive=Drives.MECANUM,
            centric=Centrics.FIELD
        )
        service.set_command_control(Commands.REMOTE)
        self.assertIsNone(service.get_snapshot()["front"])

        service.set_command_control(Commands.LOCAL, Controls.AUTOMATIC)

        self.assertEqual(Fronts.TAIL, service.get_snapshot()["front"])
        self.assertEqual(Drives.MECANUM, service.get_snapshot()["drive"])
        self.assertEqual(Centrics.FIELD, service.get_snapshot()["centric"])

    def test_remote_rejects_local_drive_selection(self):
        service = OperationModeService(command=Commands.REMOTE)
        with self.assertRaises(RuntimeError):
            service.select_local_drive()


    def test_local_drive_back_navigation_preserves_previous_selection(self):
        selector = mock.Mock()
        selector.select_setup.return_value = {"navigation": "BACK"}
        service = OperationModeService(
            local_drive_selector_port=selector,
            front=Fronts.TAIL,
            drive=Drives.MECANUM,
            centric=Centrics.FIELD
        )
        before = service.get_snapshot()

        selected = service.select_local_drive()

        self.assertEqual({"navigation": "BACK"}, selected)
        self.assertEqual(before, service.get_snapshot())

    def test_cancellation_preserves_the_last_valid_mode(self):
        selector = mock.Mock()
        selector.select_mode.return_value = None
        service = OperationModeService(
            command_control_selector_port=selector
        )
        before = service.get_snapshot()

        self.assertIsNone(service.select_command_control())
        self.assertEqual(before, service.get_snapshot())


if __name__ == "__main__":
    unittest.main()
