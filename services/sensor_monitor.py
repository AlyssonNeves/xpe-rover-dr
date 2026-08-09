#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Sensor monitoring service with optional EV3 gyroscope integration."""

from app.rover_config import (
    DRIVE_GYRO_SENSOR_CODE,
    HARDWARE_ENABLED,
    MONITOR_INTERVAL_SECONDS,
    get_sensor_definitions,
)
from services.monitor_base import MonitorBase
from services.sensor_state_store import SensorStateStore


class Ev3GyroHardwareBackend(object):
    """Small hardware backend dedicated to the standard EV3 gyroscope."""

    def __init__(self, enabled=True):
        self.available = False
        self.error = None
        self._gyro_class = None
        if not enabled:
            self.error = "Physical EV3 hardware is disabled"
            return
        try:
            from ev3dev2.sensor.lego import GyroSensor
            self._gyro_class = GyroSensor
            self.available = True
        except Exception as error:  # pragma: no cover - depends on EV3 runtime
            self.error = str(error)

    def connect(self, definition):
        if not self.available or self._gyro_class is None:
            return None
        try:
            sensor = self._gyro_class(address=definition.get("address"))
            mode = definition.get("mode")
            if mode:
                sensor.mode = mode
            return sensor
        except Exception as error:  # pragma: no cover - physical hardware path
            self.error = str(error)
            return None

    @staticmethod
    def read_angle(sensor):
        if sensor is None:
            return None
        try:
            if hasattr(sensor, "angle"):
                return float(sensor.angle)
            return float(sensor.value(0))
        except Exception:  # pragma: no cover - physical hardware path
            return None


class SensorMonitor(MonitorBase):
    """Publishes configured sensors and refreshes the EV3 gyro when available."""

    def __init__(
        self, state_store=None, interval_seconds=None, gyro_backend=None
    ):
        interval = (
            MONITOR_INTERVAL_SECONDS
            if interval_seconds is None
            else interval_seconds
        )
        MonitorBase.__init__(self, "SensorMonitor", interval)
        self.state_store = state_store or SensorStateStore()
        self.sensor_definitions = get_sensor_definitions()
        self.gyro_backend = gyro_backend or Ev3GyroHardwareBackend(
            enabled=HARDWARE_ENABLED
        )
        self._gyro = None
        self._load_configured_sensors()
        self._connect_gyro()

    def _load_configured_sensors(self):
        for code, definition in self.sensor_definitions.items():
            sensor = dict(definition)
            sensor.update({
                "code": code,
                "value": None,
                "connected": False,
                "source": "configured"
            })
            self.state_store.update_sensor(code, sensor)

    def _connect_gyro(self):
        definition = self.sensor_definitions.get(DRIVE_GYRO_SENSOR_CODE)
        if definition is not None:
            self._gyro = self.gyro_backend.connect(definition)
        self._refresh_gyro_state()

    def _refresh_gyro_state(self):
        sensor = self.state_store.get_sensor(DRIVE_GYRO_SENSOR_CODE)
        if sensor is None:
            return
        value = self.gyro_backend.read_angle(self._gyro)
        sensor["value"] = value
        sensor["connected"] = self._gyro is not None and value is not None
        sensor["source"] = (
            "ev3dev2" if sensor["connected"] else (
                "unavailable" if HARDWARE_ENABLED else "disabled"
            )
        )
        if not sensor["connected"] and self.gyro_backend.error:
            sensor["error"] = self.gyro_backend.error
        else:
            sensor.pop("error", None)
        self.state_store.update_sensor(DRIVE_GYRO_SENSOR_CODE, sensor)

    def on_cycle(self):
        """Refreshes the gyroscope; other sensor drivers remain deferred."""
        self._refresh_gyro_state()

    def list_sensors(self):
        return [
            {
                "code": item["code"],
                "name": item["name"],
                "address": item["address"],
                "connected": item["connected"]
            }
            for item in self.state_store.get_all_sensors()
        ]

    def read_sensor(self, code):
        return self.state_store.get_sensor(code)

    def read_all_sensors(self):
        return self.state_store.get_all_sensors()
