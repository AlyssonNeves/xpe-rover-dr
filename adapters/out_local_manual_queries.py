#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only query adapters for the minimal LOCAL + MANUAL runtime."""

import copy

from ports.controller_port import ControllerPort
from ports.motor_port import MotorPort
from ports.sensor_port import SensorPort


class LocalManualSensorQueryAdapter(SensorPort):
    """Exposes configured sensor metadata without starting SensorMonitor."""

    def __init__(self, sensor_definitions=None):
        self._sensors = {}
        for code, definition in (sensor_definitions or {}).items():
            item = copy.deepcopy(definition)
            item.update({
                "code": code,
                "connected": False,
                "hardware_error": None,
                "value": None,
                "monitoring": False,
                "control_source": "local_manual"
            })
            self._sensors[code] = item

    def list_sensors(self):
        return [{
            "code": item.get("code"),
            "name": item.get("name"),
            "address": item.get("address"),
            "connected": item.get("connected", False)
        } for item in self.read_all_sensors()]

    def read_sensor(self, code):
        item = self._sensors.get(code)
        return copy.deepcopy(item) if item is not None else None

    def read_all_sensors(self):
        return [copy.deepcopy(item) for item in self._sensors.values()]


class LocalManualMotorQueryAdapter(MotorPort):
    """Exposes manual motor snapshots while rejecting queued motor writes."""

    READ_ONLY_ERROR = (
        "Motor writes are unavailable while LOCAL + MANUAL control owns "
        "the motor hardware."
    )

    def __init__(self, state_store, motor_definitions=None):
        if state_store is None:
            raise ValueError("state_store is required.")
        self._state_store = state_store
        for code, definition in (motor_definitions or {}).items():
            item = copy.deepcopy(definition)
            item.update({
                "code": code,
                "connected": False,
                "hardware_error": None,
                "command": None,
                "speed_sp": 0,
                "running": False,
                "control_source": "local_manual"
            })
            self._state_store.update_motor(code, item)

    def list_motors(self):
        return [{
            "code": item.get("code"),
            "name": item.get("name"),
            "address": item.get("address"),
            "connected": item.get("connected", False)
        } for item in self.read_all_motors()]

    def read_motor(self, motor_code):
        return self._state_store.get_motor(motor_code)

    def read_all_motors(self):
        return self._state_store.get_all_motors()

    @classmethod
    def _rejected(cls):
        return {"accepted": False, "success": False, "error": cls.READ_ONLY_ERROR}

    def stop_motor(self, motor_code, stop_action=None):
        del motor_code, stop_action
        return self._rejected()

    def run_timed_motor(self, motor_code, speed_sp, time_sp, priority=None,
                        stop_action=None, timeout_ms=None):
        del motor_code, speed_sp, time_sp, priority, stop_action, timeout_ms
        return self._rejected()

    def run_forever_motor(self, motor_code, speed_sp, priority=None,
                          stop_action=None, watchdog_ms=None, timeout_ms=None):
        del motor_code, speed_sp, priority, stop_action, watchdog_ms, timeout_ms
        return self._rejected()

    def run_to_rel_pos_motor(self, motor_code, speed_sp, position_sp,
                             priority=None, stop_action=None, timeout_ms=None):
        del motor_code, speed_sp, position_sp, priority, stop_action, timeout_ms
        return self._rejected()

    def reset_motor(self, motor_code, priority=None):
        del motor_code, priority
        return self._rejected()

    def get_command(self, command_id):
        del command_id
        return None

    def list_commands(self, motor_code=None):
        del motor_code
        return []

    def cancel_motor_commands(self, motor_code):
        del motor_code
        return self._rejected()

    def run_synchronized_motors(self, commands):
        del commands
        return self._rejected()

    def execute_guarded_operation(self, motor_codes, operation_name, operation):
        del motor_codes, operation_name, operation
        return self._rejected()

    def begin_guarded_operation(self, motor_codes, operation_name, operation_id):
        del motor_codes, operation_name, operation_id
        return self._rejected()

    def end_guarded_operation(self, operation_id, status="COMPLETED",
                              error=None, stop=False):
        del operation_id, status, error, stop
        return self._rejected()


class LocalManualControllerQueryAdapter(ControllerPort):
    """Provides stable controller snapshots without ControllerMonitor."""

    def read_controller_status(self):
        return {
            "controller": "Rover Controller",
            "status": "available",
            "connected": True,
            "mode": "local_manual"
        }

    def read_network_status(self):
        return {
            "hostname": "rover-controller",
            "ip_address": "0.0.0.0",
            "mac_address": None,
            "connected": False,
            "mode": "on_demand"
        }

    def read_battery_status(self):
        return {
            "voltage": None,
            "current": None,
            "percentage": None,
            "status": "unknown",
            "mode": "on_demand"
        }

    def read_system_status(self):
        return {
            "cpu_usage": None,
            "memory_usage": None,
            "disk_usage": None,
            "uptime": None,
            "mode": "on_demand"
        }
