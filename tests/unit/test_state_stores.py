#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automated unit tests for Rover in-memory state stores.
"""

import unittest

from infrastructure.state.controller_state_store import ControllerStateStore
from infrastructure.state.motor_state_store import MotorStateStore
from infrastructure.state.sensor_state_store import SensorStateStore


class SensorStateStoreTestCase(unittest.TestCase):
    """Validates sensor state repository behavior."""

    def test_update_get_and_clear_sensor(self):
        """Sensor store must save, retrieve, isolate, and clear data."""
        store = SensorStateStore()
        source = {
            "code": "us1",
            "value": 25
        }

        store.update_sensor("us1", source)
        source["value"] = 99

        stored = store.get_sensor("us1")
        stored["value"] = 10

        self.assertEqual(25, store.get_sensor("us1")["value"])
        self.assertEqual([{"code": "us1", "value": 25}], store.get_all_sensors())

        store.clear()

        self.assertIsNone(store.get_sensor("us1"))
        self.assertEqual([], store.get_all_sensors())

    def test_returns_none_for_unknown_sensor(self):
        """Unknown sensors must return None."""
        store = SensorStateStore()

        self.assertIsNone(store.get_sensor("missing"))


class MotorStateStoreTestCase(unittest.TestCase):
    """Validates motor state repository behavior."""

    def test_update_get_and_clear_motor(self):
        """Motor store must save, retrieve, isolate, and clear data."""
        store = MotorStateStore()
        source = {
            "code": "left",
            "speed_sp": 100
        }

        store.update_motor("left", source)
        source["speed_sp"] = 999

        stored = store.get_motor("left")
        stored["speed_sp"] = 0

        self.assertEqual(100, store.get_motor("left")["speed_sp"])
        self.assertEqual(
            [{"code": "left", "speed_sp": 100}],
            store.get_all_motors()
        )

        store.clear()

        self.assertIsNone(store.get_motor("left"))
        self.assertEqual([], store.get_all_motors())

    def test_returns_none_for_unknown_motor(self):
        """Unknown motors must return None."""
        store = MotorStateStore()

        self.assertIsNone(store.get_motor("missing"))


class ControllerStateStoreTestCase(unittest.TestCase):
    """Validates controller state repository behavior."""

    def test_update_get_and_clear_controller_sections(self):
        """Controller store must isolate and clear all state sections."""
        store = ControllerStateStore()

        controller = {
            "connected": True
        }
        network = {
            "ip": "127.0.0.1"
        }
        battery = {
            "voltage": 7.4
        }
        system = {
            "platform": "test"
        }

        store.update_controller_status(controller)
        store.update_network_status(network)
        store.update_battery_status(battery)
        store.update_system_status(system)

        controller["connected"] = False
        network["ip"] = "changed"
        battery["voltage"] = 0
        system["platform"] = "changed"

        self.assertEqual(
            {"connected": True},
            store.get_controller_status()
        )
        self.assertEqual({"ip": "127.0.0.1"}, store.get_network_status())
        self.assertEqual({"voltage": 7.4}, store.get_battery_status())
        self.assertEqual({"platform": "test"}, store.get_system_status())

        returned = store.get_controller_status()
        returned["connected"] = False

        self.assertEqual(
            {"connected": True},
            store.get_controller_status()
        )

        store.clear()

        self.assertEqual({}, store.get_controller_status())
        self.assertEqual({}, store.get_network_status())
        self.assertEqual({}, store.get_battery_status())
        self.assertEqual({}, store.get_system_status())


if __name__ == "__main__":
    unittest.main()
