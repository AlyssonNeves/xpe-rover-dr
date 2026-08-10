#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shared test doubles used by the automated unit test suite.
"""

from ports.application_concurrency_port import ApplicationConcurrencyPort
from ports.process_control_port import ProcessControlPort


class FakeSensorPort(object):
    """Test double for sensor output port operations."""

    def __init__(self):
        """Initializes fake sensor data."""
        self.sensors = {
            "us1": {
                "code": "us1",
                "type": "ultrasonic",
                "value": 25
            }
        }
        self.modes = {
            "us1": ["CM", "IN"]
        }
        self.changed_modes = []

    def list_sensors(self):
        """Returns available sensors."""
        return ["us1"]

    def read_sensor(self, code):
        """Returns one sensor by code."""
        return self.sensors.get(code)

    def read_all_sensors(self):
        """Returns all sensors."""
        return list(self.sensors.values())

    def list_sensor_modes(self, code):
        """Returns available modes for a sensor."""
        return self.modes.get(code)

    def change_sensor_mode(self, code, mode):
        """Changes a sensor mode."""
        if code not in self.sensors:
            return None

        self.changed_modes.append((code, mode))

        return {
            "code": code,
            "mode": mode
        }


class FakeMotorPort(object):
    """Test double for motor output port operations."""

    def __init__(self):
        """Initializes fake motor data."""
        self.motors = {
            "left": {
                "code": "left",
                "speed_sp": 0,
                "state": "idle"
            }
        }
        self.run_timed_calls = []
        self.run_forever_calls = []
        self.run_direct_calls = []
        self.run_to_rel_pos_calls = []
        self.reset_calls = []
        self.stop_calls = []

    def list_motors(self):
        """Returns available motors."""
        return ["left"]

    def read_motor(self, code):
        """Returns one motor by code."""
        return self.motors.get(code)

    def read_all_motors(self):
        """Returns all motors."""
        return list(self.motors.values())

    def stop_motor(self, code):
        """Stops one motor."""
        if code not in self.motors:
            return None

        self.stop_calls.append(code)

        return {
            "code": code,
            "state": "stopped"
        }

    def run_timed_motor(self, code, speed_sp, time_sp, priority=None, profile=None):
        """Runs one motor for a configured time."""
        if code not in self.motors:
            return None

        self.run_timed_calls.append((code, speed_sp, time_sp))

        return {
            "code": code,
            "speed_sp": speed_sp,
            "time_sp": time_sp
        }

    def run_forever_motor(self, code, speed_sp, priority=None, profile=None):
        """Runs one motor continuously."""
        if code not in self.motors:
            return None

        self.run_forever_calls.append((code, speed_sp))

        return {
            "code": code,
            "speed_sp": speed_sp
        }

    def run_direct_motor(self, code, duty_cycle_sp, priority=None, watchdog_ms=None, timeout_ms=None, stop_action=None):
        """Runs one motor using direct duty-cycle control."""
        if code not in self.motors:
            return None
        self.run_direct_calls.append((code, duty_cycle_sp))
        return {"code": code, "duty_cycle_sp": duty_cycle_sp}

    def run_to_rel_pos_motor(self, code, speed_sp, position_sp, priority=None, profile=None):
        """Runs one motor to a relative position."""
        if code not in self.motors:
            return None

        self.run_to_rel_pos_calls.append((code, speed_sp, position_sp))

        return {
            "code": code,
            "speed_sp": speed_sp,
            "position_sp": position_sp
        }

    def reset_motor(self, code):
        """Resets one motor."""
        if code not in self.motors:
            return None

        self.reset_calls.append(code)

        return {
            "code": code,
            "state": "reset"
        }

    def cancel_motor_commands(self, code):
        """Cancels motor commands."""
        if code not in self.motors:
            return None

        return {
            "code": code,
            "state": "cancelled"
        }

    def run_synchronized_motors(self, commands):
        """Runs synchronized motor commands."""
        return {
            "success": True,
            "batch_id": 1,
            "motors": commands
        }


class FakeControllerPort(object):
    """Test double for controller output port operations."""

    def __init__(self):
        """Initializes fake controller data."""
        self.status = {
            "connected": True
        }
        self.network = {
            "ip": "127.0.0.1"
        }
        self.battery = {
            "voltage": 7.4
        }
        self.system = {
            "platform": "test"
        }

    def read_controller_status(self):
        """Returns controller status."""
        return self.status

    def read_network_status(self):
        """Returns controller network status."""
        return self.network

    def read_battery_status(self):
        """Returns controller battery status."""
        return self.battery

    def read_system_status(self):
        """Returns controller system status."""
        return self.system

class FakeRoverStateQueryPort(object):
    """Test double for consolidated Rover state query operations."""

    def __init__(self):
        """Initializes fake state."""
        self.state = {
            "controller": {
                "connected": True
            },
            "sensors": [],
            "motors": []
        }

    def get_rover_state(self):
        """Returns consolidated Rover state."""
        return self.state


class FakeDriveMotorPort(object):
    """Test double for high-level differential-drive operations."""

    def __init__(self):
        """Initializes encoder positions and recorded drive calls."""
        self.positions = {"LLM": 0.0, "RLM": 0.0}
        self.drive_calls = []
        self.stop_calls = []
        self.sync_calls = []

    def read_motor(self, code):
        """Returns the configured encoder position for one drive motor."""
        return {"code": code, "position": self.positions[code]}

    def drive_tank(self, left, right, **options):
        """Records a tank-drive request and advances the fake encoders."""
        self.drive_calls.append((left, right, options))
        self.positions["LLM"] += left * 0.1
        self.positions["RLM"] += right * 0.1
        return {"success": True}

    def stop_drive(self, stop_action=None):
        """Records a drive stop request."""
        self.stop_calls.append(stop_action)
        return {"success": True}

    def run_synchronized_motors(self, commands):
        """Records synchronized motor commands."""
        self.sync_calls.append(commands)
        return {"success": True}


class FakeDriveSensorPort(object):
    """Test double for the gyroscope used by high-level navigation."""

    def __init__(self):
        """Initializes the fake gyroscope angle."""
        self.angle = 0.0

    def read_sensor(self, code):
        """Returns the current fake gyroscope angle."""
        return {"code": code, "value": self.angle}


class FakeApplicationConcurrency(ApplicationConcurrencyPort):
    """Deterministic synchronous fake for application lifecycle tests."""

    def __init__(self):
        self.stopped = False
        self.stop_completed = False
        self.restart_requested = False
        self.lifecycle_request_claimed = False
        self.async_calls = 0

    def claim_stop(self):
        if self.stopped:
            return False
        self.stopped = True
        return True

    def is_stop_requested(self):
        return self.stopped

    def wait_for_stop_completed(self, timeout_seconds):
        del timeout_seconds
        return self.stop_completed

    def mark_stop_completed(self):
        self.stop_completed = True

    def claim_shutdown_request(self):
        return self._claim_lifecycle_request(restart_requested=False)

    def claim_restart_request(self):
        return self._claim_lifecycle_request(restart_requested=True)

    def _claim_lifecycle_request(self, restart_requested):
        if self.lifecycle_request_claimed or self.stopped:
            return False
        self.lifecycle_request_claimed = True
        self.restart_requested = bool(restart_requested)
        return True

    def is_restart_requested(self):
        return self.restart_requested

    def claim_critical_shutdown(self):
        return self.claim_shutdown_request()

    def run_async(self, target, name, daemon):
        del name
        del daemon
        self.async_calls += 1
        target()
        return None

    @staticmethod
    def is_current_component(component):
        del component
        return False


class FakeProcessControl(ProcessControlPort):
    """Records process restart requests without replacing the test process."""

    def __init__(self):
        self.restart_calls = 0

    def restart_current_process(self):
        self.restart_calls += 1

