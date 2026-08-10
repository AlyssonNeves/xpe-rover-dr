#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dedicated physical gyro monitor for FIELD-centric manual control."""

import time

from infrastructure.monitoring.monitor_base import MonitorBase


class GyroHeadingMonitor(MonitorBase):
    """Polls only the configured gyro and publishes the latest heading."""

    def __init__(self, heading_sensor_port, state_store, sensor_code="GYR",
                 address="in3", mode="GYRO-ANG", interval_seconds=0.02,
                 max_consecutive_failures=3, clock=None):
        MonitorBase.__init__(
            self,
            name="GyroHeadingMonitor",
            interval_seconds=max(0.005, float(interval_seconds))
        )
        self._sensor = heading_sensor_port
        self._state_store = state_store
        self._sensor_code = sensor_code
        self._address = address
        self._mode = mode
        self._max_consecutive_failures = max(
            1, int(max_consecutive_failures)
        )
        self._clock = clock or time.monotonic
        self._consecutive_failures = 0

    def on_initialize(self):
        self._sensor.open()
        self._sample_or_raise()

    def on_cycle(self):
        try:
            self._publish_sample()
            self._consecutive_failures = 0
        except Exception as error:
            self._consecutive_failures += 1
            self._state_store.mark_unavailable(
                error=error,
                sample_monotonic=self._clock(),
                sensor_code=self._sensor_code,
                address=self._address,
                mode=self._mode
            )
            if self._consecutive_failures >= self._max_consecutive_failures:
                raise RuntimeError(
                    "Gyro heading unavailable after {0} consecutive read "
                    "failures: {1}".format(
                        self._consecutive_failures, error
                    )
                )

    def on_finalize(self):
        self._sensor.close()

    def _sample_or_raise(self):
        try:
            self._publish_sample()
            self._consecutive_failures = 0
        except Exception as error:
            self._state_store.mark_unavailable(
                error=error,
                sample_monotonic=self._clock(),
                sensor_code=self._sensor_code,
                address=self._address,
                mode=self._mode
            )
            raise

    def _publish_sample(self):
        heading_deg = self._sensor.read_heading_deg()
        self._state_store.update(
            heading_deg=heading_deg,
            sample_monotonic=self._clock(),
            sensor_code=self._sensor_code,
            address=self._address,
            mode=self._mode
        )
