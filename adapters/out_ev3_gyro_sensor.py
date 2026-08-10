#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3Dev2 adapter for the physical LEGO EV3 gyroscope."""

import math
import time

from ports.heading_sensor_port import HeadingSensorPort


class Ev3GyroSensorAdapter(HeadingSensorPort):
    """Owns EV3 input-port preparation and gyroscope access."""

    def __init__(self, address="in3", mode="GYRO-ANG",
                 reset_on_start=True, angle_sign=1.0,
                 angle_offset_deg=0.0, port_mode=None,
                 connection_timeout_seconds=10.0,
                 connection_retry_seconds=0.1,
                 sensor_factory=None, port_factory=None,
                 clock=None, sleeper=None):
        self.address = str(address or "in3").strip()
        self.mode = str(mode or "GYRO-ANG").strip()
        self.reset_on_start = bool(reset_on_start)
        self.angle_sign = float(angle_sign)
        self.angle_offset_deg = float(angle_offset_deg)
        self.port_mode = (
            str(port_mode).strip() if port_mode is not None else None
        )
        self.connection_timeout_seconds = float(
            connection_timeout_seconds
        )
        self.connection_retry_seconds = float(
            connection_retry_seconds
        )
        if self.angle_sign not in (-1.0, 1.0):
            raise ValueError("angle_sign must be either -1.0 or 1.0.")
        if not math.isfinite(self.angle_offset_deg):
            raise ValueError("angle_offset_deg must be finite.")
        if self.connection_timeout_seconds <= 0.0:
            raise ValueError(
                "connection_timeout_seconds must be greater than zero."
            )
        if self.connection_retry_seconds <= 0.0:
            raise ValueError(
                "connection_retry_seconds must be greater than zero."
            )
        if self.connection_retry_seconds > self.connection_timeout_seconds:
            raise ValueError(
                "connection_retry_seconds must not exceed "
                "connection_timeout_seconds."
            )
        self._sensor_factory = sensor_factory
        self._port_factory = port_factory
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._sensor = None
        self._port = None

    def open(self):
        """Configures ``in3`` as UART and connects the EV3 gyro."""
        if self._sensor is not None:
            return self._sensor

        sensor_factory = self._sensor_factory
        port_factory = self._port_factory
        address = self.address
        if sensor_factory is None or (self.port_mode and port_factory is None):
            loaded = self._load_ev3_factories(self.address)
            if sensor_factory is None:
                sensor_factory = loaded[0]
            if port_factory is None:
                port_factory = loaded[1]
            address = loaded[2]

        self._prepare_input_port(port_factory, address)
        sensor = self._connect_sensor(sensor_factory, address)
        if getattr(sensor, "mode", None) != self.mode:
            sensor.mode = self.mode
        if self.reset_on_start:
            sensor.reset()
            if getattr(sensor, "mode", None) != self.mode:
                sensor.mode = self.mode
        self._sensor = sensor
        return sensor

    def read_heading_deg(self):
        """Reads canonical heading after applying mounting calibration once."""
        if self._sensor is None:
            raise RuntimeError("Gyro sensor is not open.")
        raw_heading_deg = float(self._sensor.angle)
        return (raw_heading_deg * self.angle_sign) + self.angle_offset_deg

    def close(self):
        """Releases adapter-owned references."""
        self._sensor = None
        self._port = None

    def _prepare_input_port(self, port_factory, address):
        if not self.port_mode:
            return
        if port_factory is None:
            raise RuntimeError(
                "EV3 input-port support is unavailable for gyro setup."
            )
        port = port_factory(address=address)
        available_modes = tuple(getattr(port, "modes", ()) or ())
        if available_modes and self.port_mode not in available_modes:
            raise RuntimeError(
                "Input port {0} does not support mode {1}. Available modes: "
                "{2}.".format(
                    self.address,
                    self.port_mode,
                    ", ".join(available_modes)
                )
            )
        if getattr(port, "mode", None) != self.port_mode:
            port.mode = self.port_mode
        self._port = port

    def _connect_sensor(self, sensor_factory, address):
        deadline = self._clock() + self.connection_timeout_seconds
        last_error = None
        while True:
            try:
                return sensor_factory(address=address)
            except Exception as error:
                last_error = error
                remaining = deadline - self._clock()
                if remaining <= 0.0:
                    break
                self._sleeper(min(
                    self.connection_retry_seconds,
                    remaining
                ))

        raise RuntimeError(
            "Gyroscope was not detected at {0} after configuring input "
            "port mode {1}: {2}".format(
                self.address,
                self.port_mode or "unchanged",
                last_error
            )
        )

    @staticmethod
    def _load_ev3_factories(address):
        try:
            from ev3dev2.port import LegoPort
            from ev3dev2.sensor import INPUT_1, INPUT_2, INPUT_3, INPUT_4
            from ev3dev2.sensor.lego import GyroSensor
        except ImportError as error:
            raise RuntimeError(
                "python-ev3dev2 gyro or input-port support is unavailable."
            ) from error

        normalized = str(address or "").strip()
        address_map = {
            "in1": INPUT_1,
            "in2": INPUT_2,
            "in3": INPUT_3,
            "in4": INPUT_4
        }
        return GyroSensor, LegoPort, address_map.get(normalized, normalized)
