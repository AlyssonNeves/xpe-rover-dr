#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only query adapters used by the minimal LOCAL + MANUAL graph."""

from ports.controller_port import ControllerPort
from ports.motor_query_port import MotorQueryPort
from ports.sensor_query_port import SensorQueryPort


class LocalManualSensorQueryAdapter(SensorQueryPort):
    """Exposes configured sensor metadata without a monitor thread."""

    def __init__(self, sensor_definitions=None):
        self._sensors = {}
        for code, definition in (sensor_definitions or {}).items():
            item = dict(definition)
            item.update({
                "code": code,
                "connected": False,
                "hardware_error": None,
                "mode": item.get("mode"),
                "value": None
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
        return dict(item) if item is not None else None

    def read_all_sensors(self):
        return [dict(item) for item in self._sensors.values()]

    def list_sensor_modes(self, code):
        item = self._sensors.get(code)
        return None if item is None else list(item.get("supported_modes", []))


class LocalManualMotorQueryAdapter(MotorQueryPort):
    """Exposes current manual motor state through a read-only contract."""

    def __init__(self, state_store, motor_definitions=None,
                 motor_hardware_port=None):
        self.state_store = state_store
        self._motor_hardware_port = motor_hardware_port
        self._motor_codes = tuple((motor_definitions or {}).keys())
        for code, definition in (motor_definitions or {}).items():
            item = dict(definition)
            item.update({
                "code": code,
                "connected": False,
                "hardware_error": None,
                "command": None,
                "speed_sp": 0,
                "command_state": "IDLE",
                "motion_state": "STOPPED",
                "control_source": "local_manual"
            })
            self.state_store.update_motor(code, item)

    def list_motors(self):
        return [{
            "code": item.get("code"),
            "name": item.get("name"),
            "address": item.get("address"),
            "connected": item.get("connected", False)
        } for item in self.read_all_motors()]

    def read_motor(self, motor_code):
        stored = self.state_store.get_motor(motor_code)
        if self._motor_hardware_port is None:
            return stored

        physical = self._motor_hardware_port.read_motor_state(motor_code)
        if physical is None:
            return stored

        merged = dict(stored or {})
        merged.update(physical)
        self.state_store.update_motor(motor_code, merged)
        return merged

    def read_all_motors(self):
        if self._motor_hardware_port is None:
            return self.state_store.get_all_motors()
        motors = []
        for code in self._motor_codes:
            motor = self.read_motor(code)
            if motor is not None:
                motors.append(motor)
        return motors


class LocalManualControllerQueryAdapter(ControllerPort):
    """Provides stable controller information without a polling thread."""

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


class FieldManualSensorQueryAdapter(LocalManualSensorQueryAdapter):
    """Adds one live cached gyro reading to the minimal manual query graph."""

    def __init__(self, sensor_definitions, gyro_sensor_code,
                 heading_query_port):
        LocalManualSensorQueryAdapter.__init__(
            self, sensor_definitions=sensor_definitions
        )
        self._gyro_sensor_code = gyro_sensor_code
        self._heading_query_port = heading_query_port

    def read_sensor(self, code):
        item = LocalManualSensorQueryAdapter.read_sensor(self, code)
        if item is None or code != self._gyro_sensor_code:
            return item
        snapshot = self._heading_query_port.get_heading_snapshot()
        item.update({
            "connected": bool(snapshot.get("fresh")),
            "hardware_error": snapshot.get("error"),
            "value": (
                snapshot.get("heading_deg")
                if snapshot.get("fresh") else None
            ),
            "sample_age_seconds": snapshot.get("age_seconds")
        })
        return item

    def read_all_sensors(self):
        return [
            self.read_sensor(code)
            for code in self._sensors
        ]
