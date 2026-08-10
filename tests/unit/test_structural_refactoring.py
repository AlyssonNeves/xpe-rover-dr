#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for structural dispatchers and registries introduced by refactoring."""

import unittest

from adapters.rest.routing import RouteDispatcher
from infrastructure.motor.registries import GuardedOperationRegistry, MotorCommandRegistry


class RouteDispatcherTests(unittest.TestCase):
    def test_resolves_static_and_parameterized_routes(self):
        dispatcher = RouteDispatcher()
        dispatcher.add("GET", ("api", "motors", "{code}"), "read_motor")
        name, params = dispatcher.resolve("GET", ["api", "motors", "left"])
        self.assertEqual("read_motor", name)
        self.assertEqual({"code": "left"}, params)

    def test_returns_none_for_unmatched_route(self):
        dispatcher = RouteDispatcher()
        name, params = dispatcher.resolve("POST", ["api", "missing"])
        self.assertIsNone(name)
        self.assertIsNone(params)


class MotorCommandRegistryTests(unittest.TestCase):
    def test_command_registry_returns_defensive_snapshots(self):
        registry = MotorCommandRegistry()
        registry.create(
            command_id=1,
            motor_code="left",
            action="run_forever",
            priority=0,
            batch_id=None,
            queued_at=1.0,
            parameters={}
        )
        self.assertFalse(hasattr(registry, "items"))
        self.assertFalse(hasattr(registry, "lock"))
        snapshot = registry.get(1)
        snapshot["status"] = "CHANGED"
        self.assertEqual("QUEUED", registry.get(1)["status"])
        registry.update(1, "RUNNING", started=True)
        self.assertEqual("RUNNING", registry.get(1)["status"])
        self.assertTrue(registry.get(1)["started"])

    def test_guarded_registry_rejects_conflicting_reservations(self):
        registry = GuardedOperationRegistry()
        self.assertFalse(hasattr(registry, "active_motor_codes"))
        self.assertFalse(hasattr(registry, "operations"))
        self.assertFalse(hasattr(registry, "history"))
        self.assertFalse(hasattr(registry, "lock"))
        registry.reserve("op-1", ["left"], "first")
        with self.assertRaises(RuntimeError):
            registry.reserve("op-2", ["left"], "second")
        completed = registry.release("op-1")
        self.assertEqual("COMPLETED", completed["status"])
        self.assertFalse(registry.is_reserved("left"))


if __name__ == "__main__":
    unittest.main()
