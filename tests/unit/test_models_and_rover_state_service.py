#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automated unit tests for models and Rover state consolidation.
"""

import re
import unittest

from app.operation_mode_service import (
    Centrics, Drives, Fronts, OperationModeService
)
from app.models import CommandResult, ResultStatuses
from app.services.rover_state_service import RoverStateService
from ports.monitor_diagnostics_port import MonitorDiagnosticsPort

from tests.unit.fakes import (
    FakeControllerPort,
    FakeMotorPort,
    FakeSensorPort
)


class FakeMonitor(MonitorDiagnosticsPort):
    """Test double for monitor diagnostic state."""

    def get_failure_state(self):
        """Returns fake failure state."""
        return {
            "failed": True,
            "critical": True,
            "failure_type": "RuntimeError",
            "failure_message": "boom"
        }


class CommandResultTestCase(unittest.TestCase):
    """Validates command result serialization."""

    def test_to_dict_preserves_explicit_empty_data(self):
        """Explicit empty data values must be serialized."""
        result = CommandResult(
            success=True,
            data={}
        )

        self.assertEqual(
            {
                "success": True,
                "status": ResultStatuses.SUCCESS,
                "data": {}
            },
            result.to_dict()
        )

    def test_to_dict_includes_error_only_when_present(self):
        """Errors must be serialized only when not empty."""
        result = CommandResult(
            success=False,
            status=ResultStatuses.INVALID_ARGUMENT,
            error="Invalid command"
        )

        self.assertEqual(
            {
                "success": False,
                "status": ResultStatuses.INVALID_ARGUMENT,
                "error": "Invalid command"
            },
            result.to_dict()
        )


class RoverStateServiceTestCase(unittest.TestCase):
    """Validates consolidated Rover state generation."""

    def test_builds_default_state_when_ports_are_not_configured(self):
        """Missing ports must generate safe default state sections."""
        service = RoverStateService()

        state = service.get_rover_state()

        self.assertEqual({"connected": False}, state["controller"])
        self.assertEqual([], state["sensors"])
        self.assertEqual([], state["motors"])
        self.assertEqual({}, state["system"])
        self.assertEqual({}, state["monitors"])
        self.assertIn("timestamp", state)

    def test_builds_state_from_ports_and_monitors(self):
        """Configured ports and monitors must be included in state."""
        service = RoverStateService(
            sensor_query_port=FakeSensorPort(),
            motor_query_port=FakeMotorPort(),
            controller_port=FakeControllerPort(),
            monitors={
                "sensor": FakeMonitor(),
                "motor": None
            }
        )

        state = service.get_rover_state()

        self.assertEqual({"connected": True}, state["controller"])
        self.assertEqual("us1", state["sensors"][0]["code"])
        self.assertEqual("left", state["motors"][0]["code"])
        self.assertEqual({"platform": "test"}, state["system"])

        self.assertEqual(
            {
                "failed": True,
                "critical": True,
                "failure_type": "RuntimeError",
                "failure_message": "boom"
            },
            state["monitors"]["sensor"]
        )
        self.assertEqual(
            {
                "failed": False,
                "critical": False,
                "failure_type": None,
                "failure_message": None
            },
            state["monitors"]["motor"]
        )

    def test_operation_state_uses_the_canonical_mode_snapshot(self):
        mode_service = OperationModeService(
            front=Fronts.TAIL,
            drive=Drives.MECANUM,
            centric=Centrics.CHASSIS
        )
        service = RoverStateService(operation_mode_service=mode_service)

        operation = service.get_rover_state()["operation"]

        self.assertEqual(Fronts.TAIL, operation["front"])
        self.assertEqual(Drives.MECANUM, operation["drive"])
        self.assertEqual(Centrics.CHASSIS, operation["centric"])
        self.assertNotIn("drive_system", operation)
        self.assertNotIn("mecanum_motion", operation)

    def test_operation_state_is_empty_without_a_mode_service(self):
        operation = RoverStateService().get_rover_state()["operation"]
        self.assertEqual({}, operation)

    def test_timestamp_uses_expected_api_format(self):
        """Timestamp follows the public Rover state API format."""
        service = RoverStateService()

        state = service.get_rover_state()

        self.assertIsNotNone(
            re.match(
                r"^\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$",
                state["timestamp"]
            )
        )


if __name__ == "__main__":
    unittest.main()
