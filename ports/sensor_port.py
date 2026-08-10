#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Compatibility aggregate for the sensor-query contract."""

from ports.sensor_query_port import SensorQueryPort


class SensorPort(SensorQueryPort):
    """Deprecated aggregate kept while callers migrate to SensorQueryPort."""
    pass
