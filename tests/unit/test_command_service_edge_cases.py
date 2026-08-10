#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Additional CommandService unit tests for unsupported actions and edge cases.
"""

import unittest

from app.command_service import CommandService
from app.models import CommandActions, CommandTargets, ResultStatuses
from tests.unit.fakes import (
    FakeControllerPort,
    FakeMotorPort,
    FakeRoverStateQueryPort,
    FakeSensorPort,
)


class CommandServiceAdditionalTestCase(unittest.TestCase):
    """Covers remaining CommandService branches."""

    def setUp(self):
        """Creates a fully configured command service."""
        self.sensor_port = FakeSensorPort()
        self.motor_port = FakeMotorPort()
        self.controller_port = FakeControllerPort()
        self.state_port = FakeRoverStateQueryPort()
        self.service = CommandService(
            sensor_query_port=self.sensor_port,
            sensor_command_port=self.sensor_port,
            motor_query_port=self.motor_port,
            motor_command_port=self.motor_port,
            motor_command_query_port=self.motor_port,
            drive_motor_port=self.motor_port,
            controller_port=self.controller_port,
            rover_state_query_port=self.state_port,
        )

    def test_rejects_unsupported_sensor_action(self):
        result = self.service.execute(CommandTargets.SENSOR, "bad_sensor_action")
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertIn("Unsupported sensor action", result.error)

    def test_rejects_unsupported_motor_action(self):
        result = self.service.execute(CommandTargets.MOTOR, "bad_motor_action")
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertIn("Unsupported motor action", result.error)

    def test_rejects_unsupported_controller_action(self):
        result = self.service.execute(CommandTargets.CONTROLLER, "bad_controller_action")
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertIn("Unsupported controller action", result.error)

    def test_rejects_unsupported_state_action(self):
        result = self.service.execute(CommandTargets.STATE, "bad_state_action")
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertIn("Unsupported state action", result.error)

    def test_reads_all_sensors(self):
        result = self.service.execute(
            CommandTargets.SENSOR,
            CommandActions.READ_ALL_SENSORS,
        )
        self.assertTrue(result.success)
        self.assertEqual(self.sensor_port.read_all_sensors(), result.data)

    def test_reads_all_motors(self):
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.READ_ALL_MOTORS,
        )
        self.assertTrue(result.success)
        self.assertEqual(self.motor_port.read_all_motors(), result.data)

    def test_reads_existing_motor(self):
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.READ_MOTOR,
            {"code": "left"},
        )
        self.assertTrue(result.success)
        self.assertEqual("left", result.data["code"])

    def test_read_motor_requires_code(self):
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.READ_MOTOR,
            {},
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)

    def test_read_motor_returns_not_found_for_unknown_code(self):
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.READ_MOTOR,
            {"code": "missing"},
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.NOT_FOUND, result.status)

    def test_stop_motor_requires_code(self):
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.STOP_MOTOR,
            {},
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)

    def test_stop_motor_returns_not_found_for_unknown_code(self):
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.STOP_MOTOR,
            {"code": "missing"},
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.NOT_FOUND, result.status)

    def test_run_timed_motor_returns_not_found_for_unknown_code(self):
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {"code": "missing", "speed_sp": 1, "time_sp": 1},
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.NOT_FOUND, result.status)

    def test_reads_controller_subsections(self):
        cases = [
            (CommandActions.READ_CONTROLLER_NETWORK, "ip"),
            (CommandActions.READ_CONTROLLER_BATTERY, "voltage"),
            (CommandActions.READ_CONTROLLER_SYSTEM, "platform"),
        ]
        for action, expected_key in cases:
            result = self.service.execute(CommandTargets.CONTROLLER, action)
            self.assertTrue(result.success)
            self.assertIn(expected_key, result.data)

    def test_controller_not_found_is_reported(self):
        self.controller_port.status = None
        result = self.service.execute(
            CommandTargets.CONTROLLER,
            CommandActions.READ_CONTROLLER_STATUS,
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.NOT_FOUND, result.status)

    def test_change_sensor_mode_returns_not_found_for_unknown_code(self):
        result = self.service.execute(
            CommandTargets.SENSOR,
            CommandActions.CHANGE_SENSOR_MODE,
            {"code": "missing", "mode": "CM"},
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.NOT_FOUND, result.status)

    def test_list_sensor_modes_requires_code(self):
        result = self.service.execute(
            CommandTargets.SENSOR,
            CommandActions.LIST_SENSOR_MODES,
            {},
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)


if __name__ == "__main__":
    unittest.main()

class CommandServiceMissingCodeAdditionalTestCase(unittest.TestCase):
    """Covers remaining missing-code validation branches."""

    def test_change_sensor_mode_requires_code(self):
        motor_port = FakeMotorPort()
        service = CommandService(
            sensor_query_port=FakeSensorPort(),
            sensor_command_port=FakeSensorPort(),
            motor_query_port=motor_port,
            motor_command_port=motor_port,
            motor_command_query_port=motor_port,
            drive_motor_port=motor_port
        )
        result = service.execute(
            CommandTargets.SENSOR,
            CommandActions.CHANGE_SENSOR_MODE,
            {"mode": "CM"},
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual("Missing required parameter: code", result.error)
