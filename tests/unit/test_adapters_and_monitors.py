#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automated unit tests for outbound adapters and simulated monitors.
"""

import unittest

from app.motor_lifecycle import MotorLifecycleStates
from app.services.rover_state_service import RoverStateService
from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_motor_monitor import MotorMonitorAdapter
from adapters.out_sensor_monitor import SensorMonitorAdapter
from infrastructure.monitoring.controller_monitor import ControllerMonitor
from infrastructure.state.controller_state_store import ControllerStateStore
from infrastructure.ev3.motor_driver_factory import Ev3MotorDriverFactory
from infrastructure.monitoring.motor_monitor import MotorMonitor
from infrastructure.motor.driver_repository import Ev3MotorDriverRepository
from infrastructure.state.motor_state_store import MotorStateStore
from infrastructure.monitoring.sensor_monitor import SensorMonitor
from infrastructure.state.sensor_state_store import SensorStateStore


class SensorMonitorAndAdapterTestCase(unittest.TestCase):
    """Validates sensor monitor behavior and sensor adapter delegation."""

    def setUp(self):
        """Creates an isolated sensor monitor and adapter."""
        self.state_store = SensorStateStore()
        self.monitor = SensorMonitor(
            state_store=self.state_store,
            interval_seconds=0.001
        )
        self.adapter = SensorMonitorAdapter(
            sensor_monitor=self.monitor,
            state_store=self.state_store
        )

    def test_sensor_monitor_loads_configured_sensor_registry(self):
        """Sensor monitor must publish configured sensors on startup."""
        sensors = self.state_store.get_all_sensors()
        sensor_codes = sorted(sensor["code"] for sensor in sensors)

        self.assertEqual(["GYR", "LCS", "RCS", "TCH", "TMP"], sensor_codes)

    def test_list_sensors_returns_reduced_discovery_payload(self):
        """Sensor adapter list operation must hide detailed fields."""
        sensors = self.adapter.list_sensors()
        first_sensor = sensors[0]

        self.assertIn("code", first_sensor)
        self.assertIn("name", first_sensor)
        self.assertIn("address", first_sensor)
        self.assertIn("connected", first_sensor)
        self.assertNotIn("supported_modes", first_sensor)
        self.assertNotIn("value", first_sensor)

    def test_list_sensor_modes_returns_supported_modes(self):
        """Sensor adapter must return supported modes for known sensor."""
        self.assertEqual(
            ["NXT-TEMP-C", "NXT-TEMP-F"],
            self.adapter.list_sensor_modes("TMP")
        )

    def test_list_sensor_modes_returns_none_for_unknown_sensor(self):
        """Sensor mode listing must return None for unknown sensor code."""
        self.assertIsNone(self.adapter.list_sensor_modes("UNKNOWN"))

    def test_change_sensor_mode_updates_valid_mode(self):
        """Supported sensor mode change must update the state store."""
        updated_sensor = self.adapter.change_sensor_mode("TMP", "NXT-TEMP-F")

        self.assertEqual("NXT-TEMP-F", updated_sensor["mode"])
        self.assertEqual(
            "NXT-TEMP-F",
            self.state_store.get_sensor("TMP")["mode"]
        )

    def test_change_sensor_mode_rejects_unsupported_mode(self):
        """Unsupported sensor mode must return an explicit error payload."""
        result = self.adapter.change_sensor_mode("TMP", "INVALID")

        self.assertFalse(result["success"])
        self.assertEqual("Unsupported mode for the sensor.", result["error"])
        self.assertEqual("TMP", result["sensor"]["code"])

    def test_change_sensor_mode_returns_none_for_unknown_sensor(self):
        """Mode change must return None when the sensor does not exist."""
        self.assertIsNone(self.adapter.change_sensor_mode("UNKNOWN", "MODE"))




class FakeEv3Motor(object):
    """Fake EV3 motor driver used by hardware monitoring tests."""

    def __init__(self, address):
        """Initializes deterministic fake motor values."""
        self.address = address
        self.command = "run-timed"
        self.commands = ("run-timed", "stop")
        self.count_per_rot = 360
        self.count_per_m = 0
        self.driver_name = "lego-ev3-l-motor"
        self.duty_cycle = 25
        self.duty_cycle_sp = 30
        self.polarity = "normal"
        self.position = 123
        self.position_sp = 456
        self.speed = 78
        self.speed_sp = 90
        self.state = {"running"}
        self.stop_action = "brake"
        self.stop_actions = ("coast", "brake", "hold")
        self.time_sp = 1000
        self.stop_calls = []
        self.run_timed_calls = []
        self.run_forever_calls = []
        self.run_direct_calls = []
        self.run_to_rel_pos_calls = []
        self.reset_calls = []

    def stop(self, stop_action="brake"):
        """Records a deterministic stop command."""
        self.command = "stop"
        self.stop_action = stop_action
        self.stop_calls.append({"stop_action": stop_action})

    def run_timed(self, speed_sp, time_sp):
        """Records a deterministic timed run command."""
        self.command = "run-timed"
        self.speed_sp = speed_sp
        self.time_sp = time_sp
        self.run_timed_calls.append({
            "speed_sp": speed_sp,
            "time_sp": time_sp
        })

    def run_forever(self, speed_sp):
        """Records a deterministic continuous run command."""
        self.command = "run-forever"
        self.speed_sp = speed_sp
        self.run_forever_calls.append({
            "speed_sp": speed_sp
        })

    def run_direct(self, duty_cycle_sp):
        """Records a deterministic direct duty-cycle command."""
        self.command = "run-direct"
        self.duty_cycle_sp = duty_cycle_sp
        self.run_direct_calls.append({"duty_cycle_sp": duty_cycle_sp})

    def run_to_rel_pos(self, speed_sp, position_sp):
        """Records a deterministic relative-position command."""
        self.command = "run-to-rel-pos"
        self.speed_sp = speed_sp
        self.position_sp = position_sp
        self.run_to_rel_pos_calls.append({
            "speed_sp": speed_sp,
            "position_sp": position_sp
        })

    def reset(self):
        """Records a deterministic reset command."""
        self.command = "reset"
        self.position = 0
        self.reset_calls.append({})


class FailingCommandEv3Motor(FakeEv3Motor):
    """Fake EV3 motor driver that fails during command execution."""

    def stop(self, stop_action="brake"):
        """Raises a deterministic stop command error."""
        raise RuntimeError("stop failed")

    def run_timed(self, speed_sp, time_sp):
        """Raises a deterministic timed command error."""
        raise RuntimeError("run timed failed")

    def run_forever(self, speed_sp):
        """Raises a deterministic continuous command error."""
        raise RuntimeError("run forever failed")

    def run_to_rel_pos(self, speed_sp, position_sp):
        """Raises a deterministic relative-position command error."""
        raise RuntimeError("run to rel pos failed")

    def reset(self):
        """Raises a deterministic reset command error."""
        raise RuntimeError("reset failed")


class FailingEv3Motor(object):
    """Fake EV3 motor driver that fails during connection."""

    def __init__(self, address):
        """Raises a connection error."""
        raise RuntimeError("motor is disconnected")


class FakeMotorHardwareBackend(object):
    """Fake EV3 motor backend used by motor monitor tests."""

    def __init__(
        self,
        available=True,
        error_message=None,
        motor_classes=None
    ):
        """Initializes the fake backend."""
        self.available = available
        self.error_message = error_message
        self._motor_classes = motor_classes or {
            "LargeMotor": object,
            "MediumMotor": object
        } if available else {}

    def is_available(self):
        """Returns the configured fake availability state."""
        return self.available

    def get_motor_class(self, motor_class_name):
        """Returns a fake motor class when available."""
        return self._motor_classes.get(motor_class_name)

    def create_motor(self, motor_definition):
        """Creates a configured fake motor through the shared factory API."""
        motor_class = self.get_motor_class(
            motor_definition.get("motor_class")
        )
        if motor_class is None:
            raise RuntimeError("Motor driver class is not available.")
        return motor_class(motor_definition.get("address"))


class MotorMonitorAndAdapterTestCase(unittest.TestCase):
    """Validates motor monitor behavior and motor adapter delegation."""

    def setUp(self):
        """Creates an isolated motor monitor and adapter."""
        self.state_store = MotorStateStore()
        self.monitor = MotorMonitor(
            state_store=self.state_store,
            interval_seconds=0.001,
            hardware_enabled=False
        )
        self.adapter = MotorMonitorAdapter(
            motor_monitor=self.monitor,
            state_store=self.state_store
        )

    def test_motor_monitor_loads_initial_motor_repository(self):
        """Motor monitor must publish the configured motor registry."""
        motors = self.state_store.get_all_motors()
        motor_codes = sorted(motor["code"] for motor in motors)

        self.assertEqual(["LLM", "LMM", "RLM", "RMM"], motor_codes)


    def test_motor_monitor_uses_injected_motor_definitions(self):
        """Motor monitor must consume external motor definitions."""
        store = MotorStateStore()
        motor_definitions = {
            "TST": {
                "name": "Test Motor",
                "address": "outA",
                "motor_class": "LargeMotor"
            }
        }

        MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions=motor_definitions,
            hardware_enabled=False
        )

        motor = store.get_motor("TST")

        self.assertEqual("TST", motor["code"])
        self.assertEqual("Test Motor", motor["name"])
        self.assertEqual("outA", motor["address"])
        self.assertEqual("LargeMotor", motor["motor_class"])
        self.assertTrue(motor["connected"])
        self.assertFalse(motor["hardware_enabled"])

    def test_motor_monitor_marks_hardware_mode_in_initial_state(self):
        """Initial motor state must expose hardware mode configuration."""
        store = MotorStateStore()

        MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions={
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outD",
                    "motor_class": "MediumMotor"
                }
            },
            hardware_enabled=True
        )

        motor = store.get_motor("HW")

        self.assertFalse(motor["connected"])
        self.assertTrue(motor["hardware_enabled"])


    def test_ev3_motor_hardware_backend_handles_missing_dependency(self):
        """EV3 backend must fail safely when ev3dev2 is unavailable."""
        backend = Ev3MotorDriverFactory()

        if backend.is_available():
            self.assertIsNotNone(backend.get_motor_class("LargeMotor"))
            self.assertIsNotNone(backend.get_motor_class("MediumMotor"))
        else:
            self.assertIsNone(backend.get_motor_class("LargeMotor"))

    def test_motor_monitor_exposes_available_hardware_backend_metadata(self):
        """Hardware mode must expose loaded EV3 backend metadata."""
        store = MotorStateStore()

        MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions={
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            hardware_enabled=True,
            hardware_backend=FakeMotorHardwareBackend(available=True)
        )

        motor = store.get_motor("HW")

        self.assertTrue(motor["hardware_enabled"])
        self.assertTrue(motor["hardware_backend_available"])
        self.assertTrue(motor["driver_class_loaded"])
        self.assertEqual(
            MotorLifecycleStates.HARDWARE_READY,
            motor["lifecycle_state"]
        )
        self.assertIsNone(motor["hardware_error"])

    def test_motor_monitor_exposes_unavailable_hardware_backend_metadata(self):
        """Hardware mode must expose driver loading failures safely."""
        store = MotorStateStore()

        MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions={
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outD",
                    "motor_class": "MediumMotor"
                }
            },
            hardware_enabled=True,
            hardware_backend=FakeMotorHardwareBackend(
                available=False,
                error_message="ev3dev2 is not installed"
            )
        )

        motor = store.get_motor("HW")

        self.assertFalse(motor["connected"])
        self.assertTrue(motor["hardware_enabled"])
        self.assertFalse(motor["hardware_backend_available"])
        self.assertFalse(motor["driver_class_loaded"])
        self.assertEqual("HARDWARE_UNAVAILABLE", motor["lifecycle_state"])
        self.assertEqual("ev3dev2 is not installed", motor["hardware_error"])

    def test_motor_repository_reads_physical_motor_snapshot_safely(self):
        """Motor registry must read JSON-friendly hardware snapshots."""
        motor_definitions = {
            "HW": {
                "name": "Hardware Motor",
                "address": "outA",
                "motor_class": "LargeMotor"
            }
        }
        registry = Ev3MotorDriverRepository(
            motor_definitions,
            FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FakeEv3Motor}
            )
        )

        snapshot = registry.read_motor("HW")

        self.assertEqual("HW", snapshot["code"])
        self.assertEqual("outA", snapshot["address"])
        self.assertTrue(snapshot["connected"])
        self.assertEqual("CONNECTED", snapshot["lifecycle_state"])
        self.assertEqual(123, snapshot["position"])
        self.assertEqual(78, snapshot["speed"])
        self.assertEqual(["running"], snapshot["state"])
        self.assertEqual(["run-timed", "stop"], snapshot["commands"])

    def test_motor_repository_reports_disconnected_motor_safely(self):
        """Motor registry must report connection failures safely."""
        motor_definitions = {
            "HW": {
                "name": "Hardware Motor",
                "address": "outA",
                "motor_class": "LargeMotor"
            }
        }
        registry = Ev3MotorDriverRepository(
            motor_definitions,
            FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FailingEv3Motor}
            )
        )

        snapshot = registry.read_motor("HW")

        self.assertFalse(snapshot["connected"])
        self.assertEqual("DISCONNECTED", snapshot["lifecycle_state"])
        self.assertEqual("motor is disconnected", snapshot["hardware_error"])

    def test_motor_repository_executes_physical_stop_command(self):
        """Motor registry must delegate stop commands to the driver."""
        registry = Ev3MotorDriverRepository(
            {
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FakeEv3Motor}
            )
        )

        result = registry.execute_stop("HW")
        motor = registry._motors["HW"]  # pylint: disable=protected-access

        self.assertTrue(result["success"])
        self.assertEqual([{"stop_action": "brake"}], motor.stop_calls)

    def test_motor_repository_executes_physical_run_timed_command(self):
        """Motor registry must delegate timed commands to the driver."""
        registry = Ev3MotorDriverRepository(
            {
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FakeEv3Motor}
            )
        )

        result = registry.execute_run_timed("HW", 250, 1000)
        motor = registry._motors["HW"]  # pylint: disable=protected-access

        self.assertTrue(result["success"])
        self.assertEqual(
            [{"speed_sp": 250, "time_sp": 1000}],
            motor.run_timed_calls
        )

    def test_motor_repository_reports_physical_command_failures(self):
        """Motor registry must report command execution failures safely."""
        registry = Ev3MotorDriverRepository(
            {
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FailingCommandEv3Motor}
            )
        )

        result = registry.execute_run_timed("HW", 250, 1000)

        self.assertFalse(result["success"])
        self.assertEqual("run timed failed", result["hardware_error"])

    def test_motor_monitor_executes_real_hardware_run_timed_command(self):
        """Hardware mode must execute timed commands on EV3 drivers."""
        store = MotorStateStore()
        monitor = MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions={
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            hardware_enabled=True,
            hardware_backend=FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FakeEv3Motor}
            )
        )

        motor = monitor.run_timed_motor("HW", 300, 1500)
        driver = monitor.motor_registry._motors["HW"]

        self.assertTrue(motor["success"])
        self.assertTrue(motor["hardware_command_executed"])
        self.assertEqual("COMPLETED", motor["lifecycle_state"])
        self.assertEqual(
            [{"speed_sp": 300, "time_sp": 1500}],
            driver.run_timed_calls
        )

    def test_motor_monitor_executes_real_hardware_stop_command(self):
        """Hardware mode must execute stop commands on EV3 drivers."""
        store = MotorStateStore()
        monitor = MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions={
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            hardware_enabled=True,
            hardware_backend=FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FakeEv3Motor}
            )
        )

        motor = monitor.stop_motor("HW")
        driver = monitor.motor_registry._motors["HW"]

        self.assertTrue(motor["success"])
        self.assertTrue(motor["hardware_command_executed"])
        self.assertEqual("COMPLETED", motor["lifecycle_state"])
        self.assertEqual([{"stop_action": "brake"}], driver.stop_calls)

    def test_motor_monitor_reports_hardware_command_failure(self):
        """Hardware command failures must be visible in motor state."""
        store = MotorStateStore()
        monitor = MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions={
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            hardware_enabled=True,
            hardware_backend=FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FailingCommandEv3Motor}
            )
        )

        motor = monitor.run_timed_motor("HW", 300, 1500)

        self.assertFalse(motor["success"])
        self.assertTrue(motor["hardware_command_executed"])
        self.assertEqual("COMMAND_FAILED", motor["lifecycle_state"])
        self.assertEqual("run timed failed", motor["hardware_error"])

    def test_motor_monitor_keeps_simulated_command_fallback(self):
        """Disabled hardware mode must preserve simulated commands."""
        motor = self.adapter.run_timed_motor("LLM", 250, 1000)

        self.assertTrue(motor["success"])
        self.assertFalse(motor["hardware_command_executed"])
        self.assertEqual("run-timed", motor["command"])

    def test_motor_monitor_cycle_reads_hardware_motor_state(self):
        """Hardware-enabled cycle must publish real motor snapshots."""
        store = MotorStateStore()
        monitor = MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions={
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            hardware_enabled=True,
            hardware_backend=FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FakeEv3Motor}
            )
        )

        monitor.on_cycle()
        motor = store.get_motor("HW")

        self.assertTrue(motor["connected"])
        self.assertTrue(motor["hardware_enabled"])
        self.assertTrue(motor["hardware_backend_available"])
        self.assertTrue(motor["driver_class_loaded"])
        self.assertEqual("CONNECTED", motor["lifecycle_state"])
        self.assertEqual(123, motor["position"])
        self.assertEqual(78, motor["speed"])
        self.assertEqual("lego-ev3-l-motor", motor["driver_name"])

    def test_motor_monitor_cycle_reports_disconnected_hardware_motor(self):
        """Hardware cycle must not fail when a motor is disconnected."""
        store = MotorStateStore()
        monitor = MotorMonitor(
            state_store=store,
            interval_seconds=0.001,
            motor_definitions={
                "HW": {
                    "name": "Hardware Motor",
                    "address": "outA",
                    "motor_class": "LargeMotor"
                }
            },
            hardware_enabled=True,
            hardware_backend=FakeMotorHardwareBackend(
                available=True,
                motor_classes={"LargeMotor": FailingEv3Motor}
            )
        )

        monitor.on_cycle()
        motor = store.get_motor("HW")

        self.assertFalse(motor["connected"])
        self.assertTrue(motor["hardware_backend_available"])
        self.assertEqual("DISCONNECTED", motor["lifecycle_state"])
        self.assertEqual("motor is disconnected", motor["hardware_error"])

    def test_list_motors_returns_reduced_discovery_payload(self):
        """Motor adapter list operation must hide command details."""
        motor = self.adapter.run_timed_motor("LLM", 100, 500)
        self.assertEqual("run-timed", motor["command"])

        listed_motor = self.adapter.list_motors()[0]

        self.assertIn("code", listed_motor)
        self.assertIn("name", listed_motor)
        self.assertIn("address", listed_motor)
        self.assertIn("connected", listed_motor)
        self.assertNotIn("speed_sp", listed_motor)
        self.assertNotIn("time_sp", listed_motor)

    def test_run_timed_motor_accepts_motor_code_through_adapter(self):
        """Adapter must invoke timed motor command using motor code."""
        motor = self.adapter.run_timed_motor("LLM", 250, 1000)

        self.assertEqual("LLM", motor["code"])
        self.assertEqual("run-timed", motor["command"])
        self.assertEqual(250, motor["speed_sp"])
        self.assertEqual(1000, motor["time_sp"])
        self.assertTrue(motor["success"])

    def test_run_timed_motor_returns_none_for_unknown_motor(self):
        """Timed motor command must return None for unknown motor."""
        self.assertIsNone(self.adapter.run_timed_motor("UNKNOWN", 100, 1000))

    def test_stop_motor_clears_transient_command_fields(self):
        """Stop command must clear previous transient command fields."""
        self.adapter.run_timed_motor("LLM", 250, 1000)
        stopped_motor = self.adapter.stop_motor("LLM")

        self.assertEqual("stop", stopped_motor["command"])
        self.assertTrue(stopped_motor["success"])
        self.assertNotIn("speed_sp", stopped_motor)
        self.assertNotIn("time_sp", stopped_motor)
        self.assertNotIn("position_sp", stopped_motor)
        self.assertNotIn("duty_cycle_sp", stopped_motor)

    def test_stop_motor_returns_none_for_unknown_motor(self):
        """Stop command must return None for unknown motor."""
        self.assertIsNone(self.adapter.stop_motor("UNKNOWN"))


class ControllerAndRoverStateAdapterTestCase(unittest.TestCase):
    """Validates controller and consolidated state query adapters."""

    def test_controller_monitor_publishes_simulated_controller_state(self):
        """Controller monitor must publish all simulated status blocks."""
        store = ControllerStateStore()
        monitor = ControllerMonitor(
            state_store=store,
            interval_seconds=0.001
        )
        adapter = ControllerMonitorAdapter(
            controller_monitor=monitor,
            state_store=store
        )

        self.assertEqual("Rover Controller", adapter.read_controller_status()["controller"])
        self.assertEqual("rover-controller", adapter.read_network_status()["hostname"])
        self.assertEqual("unknown", adapter.read_battery_status()["status"])
        self.assertEqual("simulated", adapter.read_system_status()["mode"])

    def test_controller_monitor_cycle_refreshes_store_values(self):
        """Controller cycle must overwrite stale simulated state."""
        store = ControllerStateStore()
        monitor = ControllerMonitor(
            state_store=store,
            interval_seconds=0.001
        )

        store.update_controller_status({"status": "stale"})
        monitor.on_cycle()

        self.assertEqual("available", store.get_controller_status()["status"])

    def test_rover_state_service_implements_query_port_directly(self):
        """The state service directly implements the application query port."""
        service = RoverStateService()

        state = service.get_rover_state()

        self.assertIn("timestamp", state)
        self.assertIn("controller", state)
        self.assertIn("sensors", state)
        self.assertIn("motors", state)
        self.assertIn("monitors", state)


if __name__ == "__main__":
    unittest.main()
