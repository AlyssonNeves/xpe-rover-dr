#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automated unit tests for app.command_service.
"""

import unittest

from app.command_service import CommandService
from app.models import CommandActions, CommandTargets, ResultStatuses

from tests.unit.fakes import (
    FakeControllerPort,
    FakeMotorPort,
    FakeRoverStateQueryPort,
    FakeSensorPort
)


class CommandServiceTestCase(unittest.TestCase):
    """Validates command dispatching, responses, and parameter validation."""

    def setUp(self):
        """Creates command service test fixture."""
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
            rover_state_query_port=self.state_port
        )

    def test_rejects_unsupported_target(self):
        """Unsupported targets must return HTTP-like 400."""
        result = self.service.execute("invalid", "anything")

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual(
            "Unsupported command target: invalid",
            result.error
        )

    def test_lists_sensors(self):
        """Sensor listing must be delegated to the sensor port."""
        result = self.service.execute(
            CommandTargets.SENSOR,
            CommandActions.LIST_SENSORS
        )

        self.assertTrue(result.success)
        self.assertEqual(["us1"], result.data)

    def test_reads_existing_sensor(self):
        """Existing sensor reads must return success."""
        result = self.service.execute(
            CommandTargets.SENSOR,
            CommandActions.READ_SENSOR,
            {
                "code": "us1"
            }
        )

        self.assertTrue(result.success)
        self.assertEqual("us1", result.data["code"])

    def test_read_sensor_requires_code(self):
        """Sensor read must reject missing code."""
        result = self.service.execute(
            CommandTargets.SENSOR,
            CommandActions.READ_SENSOR,
            {}
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual("Missing required parameter: code", result.error)

    def test_read_sensor_returns_not_found_for_unknown_code(self):
        """Unknown sensor reads must return 404."""
        result = self.service.execute(
            CommandTargets.SENSOR,
            CommandActions.READ_SENSOR,
            {
                "code": "unknown"
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.NOT_FOUND, result.status)
        self.assertEqual("Sensor not found: unknown", result.error)

    def test_change_sensor_mode_requires_mode(self):
        """Changing sensor mode must require mode parameter."""
        result = self.service.execute(
            CommandTargets.SENSOR,
            CommandActions.CHANGE_SENSOR_MODE,
            {
                "code": "us1"
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual("Missing required parameter: mode", result.error)

    def test_runs_timed_motor_with_valid_parameters(self):
        """Valid timed motor command must be delegated to the motor port."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {
                "code": "left",
                "speed_sp": 300,
                "time_sp": 1000
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(
            [("left", 300, 1000)],
            self.motor_port.run_timed_calls
        )
        self.assertEqual(300, result.data["speed_sp"])
        self.assertEqual(1000, result.data["time_sp"])

    def test_run_timed_motor_requires_code(self):
        """Timed motor command must reject missing motor code."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {
                "speed_sp": 300,
                "time_sp": 1000
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual("Missing required parameter: code", result.error)

    def test_run_timed_motor_requires_speed_sp(self):
        """Timed motor command must reject missing speed_sp."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {
                "code": "left",
                "time_sp": 1000
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual("Missing required parameter: speed_sp", result.error)

    def test_run_timed_motor_requires_time_sp(self):
        """Timed motor command must reject missing time_sp."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {
                "code": "left",
                "speed_sp": 300
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual("Missing required parameter: time_sp", result.error)

    def test_run_timed_motor_rejects_boolean_speed(self):
        """Boolean speed_sp must not be accepted as integer."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {
                "code": "left",
                "speed_sp": True,
                "time_sp": 1000
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual("Parameter speed_sp must be an integer", result.error)

    def test_run_timed_motor_rejects_boolean_time(self):
        """Boolean time_sp must not be accepted as integer."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {
                "code": "left",
                "speed_sp": 300,
                "time_sp": False
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual("Parameter time_sp must be an integer", result.error)

    def test_run_timed_motor_rejects_speed_outside_range(self):
        """speed_sp must respect the configured allowed range."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {
                "code": "left",
                "speed_sp": 1001,
                "time_sp": 1000
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual(
            "Parameter speed_sp must be between -1000 and 1000",
            result.error
        )

    def test_run_timed_motor_rejects_non_positive_time(self):
        """time_sp must be greater than zero."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            {
                "code": "left",
                "speed_sp": 300,
                "time_sp": 0
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual(
            "Parameter time_sp must be greater than zero",
            result.error
        )

    def test_controller_without_port_returns_service_unavailable(self):
        """Controller commands must require a configured controller port."""
        service = CommandService(
            sensor_query_port=self.sensor_port,
            sensor_command_port=self.sensor_port,
            motor_query_port=self.motor_port
        )

        result = service.execute(
            CommandTargets.CONTROLLER,
            CommandActions.READ_CONTROLLER_STATUS
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.UNAVAILABLE, result.status)
        self.assertEqual("Controller port is not configured", result.error)

    def test_reads_controller_status(self):
        """Controller status command must return controller status."""
        result = self.service.execute(
            CommandTargets.CONTROLLER,
            CommandActions.READ_CONTROLLER_STATUS
        )

        self.assertTrue(result.success)
        self.assertEqual({"connected": True}, result.data)

    def test_state_without_port_returns_service_unavailable(self):
        """State commands must require a configured state query port."""
        service = CommandService(
            sensor_query_port=self.sensor_port,
            sensor_command_port=self.sensor_port,
            motor_query_port=self.motor_port
        )

        result = service.execute(
            CommandTargets.STATE,
            CommandActions.READ_ROVER_STATE
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.UNAVAILABLE, result.status)
        self.assertEqual(
            "Rover state query port is not configured",
            result.error
        )

    def test_reads_consolidated_rover_state(self):
        """State command must return consolidated Rover state."""
        result = self.service.execute(
            CommandTargets.STATE,
            CommandActions.READ_ROVER_STATE
        )

        self.assertTrue(result.success)
        self.assertEqual(self.state_port.state, result.data)

    def test_runs_forever_motor_with_valid_parameters(self):
        """Valid continuous motor command must be delegated."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_FOREVER_MOTOR,
            {
                "code": "left",
                "speed_sp": 300
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(
            [("left", 300)],
            self.motor_port.run_forever_calls
        )
        self.assertEqual(300, result.data["speed_sp"])

    def test_run_to_rel_pos_motor_with_valid_parameters(self):
        """Valid relative-position command must be delegated."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TO_REL_POS_MOTOR,
            {
                "code": "left",
                "speed_sp": 300,
                "position_sp": 720
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(
            [("left", 300, 720)],
            self.motor_port.run_to_rel_pos_calls
        )
        self.assertEqual(720, result.data["position_sp"])

    def test_reset_motor_with_valid_parameters(self):
        """Valid reset command must be delegated."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RESET_MOTOR,
            {
                "code": "left"
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(["left"], self.motor_port.reset_calls)
        self.assertEqual("reset", result.data["state"])

    def test_run_to_rel_pos_requires_position_sp(self):
        """Relative-position commands must require position_sp."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_TO_REL_POS_MOTOR,
            {
                "code": "left",
                "speed_sp": 300
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)
        self.assertEqual(
            "Missing required parameter: position_sp",
            result.error
        )


    def test_run_direct_motor_accepts_valid_duty_cycle(self):
        """Direct control must accept duty-cycle values from -100 to 100."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_DIRECT_MOTOR,
            {"code": "left", "duty_cycle_sp": 40}
        )
        self.assertTrue(result.success)
        self.assertEqual(("left", 40), self.motor_port.run_direct_calls[-1])

    def test_run_direct_motor_rejects_out_of_range_duty_cycle(self):
        """Direct control must reject unsafe duty-cycle values."""
        result = self.service.execute(
            CommandTargets.MOTOR,
            CommandActions.RUN_DIRECT_MOTOR,
            {"code": "left", "duty_cycle_sp": 101}
        )
        self.assertFalse(result.success)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, result.status)


if __name__ == "__main__":
    unittest.main()
