#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP-level unit tests for the Rover REST API adapter."""

import http.client
import json
import socket
import threading
import time
import unittest

from adapters.in_rest_api_server import RestApiServer
from app.command_service import CommandService
from app.models import ResultStatuses
from tests.unit.fakes import (
    FakeControllerPort,
    FakeMotorPort,
    FakeRoverStateQueryPort,
    FakeSensorPort,
)


TEST_SHUTDOWN_TOKEN = "test-shutdown-token"


class FailingCommandService(object):
    """Command service test double that always raises."""

    def execute(self, target, action, payload=None):
        """Raises an unexpected exception."""
        raise RuntimeError("boom")


def get_free_port():
    """Returns an available localhost TCP port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class RestApiServerHttpTestCase(unittest.TestCase):
    """Exercises the REST adapter through real HTTP requests."""

    def setUp(self):
        """Starts a REST server with fake application ports."""
        self.sensor_port = FakeSensorPort()
        self.motor_port = FakeMotorPort()
        self.controller_port = FakeControllerPort()
        self.state_port = FakeRoverStateQueryPort()
        self.shutdown_calls = []
        self.restart_calls = []

        self.command_service = CommandService(
            sensor_query_port=self.sensor_port,
            sensor_command_port=self.sensor_port,
            motor_query_port=self.motor_port,
            motor_command_port=self.motor_port,
            motor_command_query_port=self.motor_port,
            drive_motor_port=self.motor_port,
            controller_port=self.controller_port,
            rover_state_query_port=self.state_port,
        )
        self.port = get_free_port()
        self.server = RestApiServer(
            command_service=self.command_service,
            host="127.0.0.1",
            port=self.port,
            shutdown_token=TEST_SHUTDOWN_TOKEN,
            hardware_api_token=None,
            shutdown_confirmation_required=True,
            shutdown_callback=lambda: self.shutdown_calls.append(True),
            restart_callback=lambda: self.restart_calls.append(True),
        )
        self.thread = threading.Thread(target=self.server.start)
        self.thread.daemon = True
        self.thread.start()
        self._wait_until_started()

    def tearDown(self):
        """Stops the test REST server."""
        self.server.stop()
        self.thread.join(timeout=2.0)

    def _wait_until_started(self):
        """Waits until the server accepts TCP connections."""
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=0.2)
                conn.request("OPTIONS", "/api/state")
                conn.getresponse().read()
                conn.close()
                return
            except Exception:
                time.sleep(0.01)
        self.fail("REST server did not start")

    def request(self, method, path, body=None, headers=None):
        """Executes an HTTP request and returns status, headers, and JSON body."""
        request_headers = headers or {}
        raw_body = None
        if body is not None:
            raw_body = json.dumps(body)
            request_headers.setdefault("Content-Type", "application/json")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2.0)
        conn.request(method, path, body=raw_body, headers=request_headers)
        response = conn.getresponse()
        payload = response.read()
        response_headers = dict(response.getheaders())
        conn.close()
        if payload:
            return response.status, response_headers, json.loads(payload.decode("utf-8"))
        return response.status, response_headers, None

    def test_options_returns_cors_preflight_headers(self):
        status, headers, body = self.request("OPTIONS", "/api/state")
        self.assertEqual(204, status)
        self.assertIsNone(body)
        self.assertEqual("*", headers["Access-Control-Allow-Origin"])
        self.assertIn("OPTIONS", headers["Access-Control-Allow-Methods"])

    def test_get_routes_return_successful_payloads(self):
        routes = [
            "/api/state",
            "/api/sensors",
            "/api/sensors/all",
            "/api/sensors/us1",
            "/api/sensors/us1/modes",
            "/api/motors",
            "/api/motors/all",
            "/api/motors/left",
            "/api/controller",
            "/api/controller/network",
            "/api/controller/battery",
            "/api/controller/system",
        ]
        for route in routes:
            status, headers, body = self.request("GET", route)
            self.assertEqual(200, status, route)
            self.assertTrue(body["success"], route)
            self.assertEqual(ResultStatuses.SUCCESS, body["status"], route)
            self.assertEqual(200, body["status_code"], route)
            self.assertEqual("application/json", headers["Content-Type"])

    def test_unknown_get_route_returns_404(self):
        status, headers, body = self.request("GET", "/api/unknown")
        self.assertEqual(404, status)
        self.assertFalse(body["success"])
        self.assertEqual(ResultStatuses.NOT_FOUND, body["status"])
        self.assertEqual(404, body["status_code"])
        self.assertEqual("Route not found.", body["error"])

    def test_post_run_timed_motor_executes_command(self):
        status, headers, body = self.request(
            "POST",
            "/api/motors/left/run-timed",
            {"speed_sp": 100, "time_sp": 250},
        )
        self.assertEqual(200, status)
        self.assertTrue(body["success"])
        self.assertEqual(("left", 100, 250), self.motor_port.run_timed_calls[-1])


    def test_post_run_forever_motor_executes_command(self):
        status, headers, body = self.request(
            "POST",
            "/api/motors/left/run-forever",
            {"speed_sp": 100},
        )
        self.assertEqual(200, status)
        self.assertTrue(body["success"])
        self.assertEqual(("left", 100), self.motor_port.run_forever_calls[-1])

    def test_post_run_to_rel_pos_motor_executes_command(self):
        status, headers, body = self.request(
            "POST",
            "/api/motors/left/run-to-rel-pos",
            {"speed_sp": 100, "position_sp": 720},
        )
        self.assertEqual(200, status)
        self.assertTrue(body["success"])
        self.assertEqual(
            ("left", 100, 720),
            self.motor_port.run_to_rel_pos_calls[-1]
        )

    def test_post_reset_motor_accepts_empty_json_object(self):
        status, headers, body = self.request(
            "POST",
            "/api/motors/left/reset",
            {},
        )
        self.assertEqual(200, status)
        self.assertTrue(body["success"])
        self.assertEqual("left", self.motor_port.reset_calls[-1])

    def test_post_stop_motor_accepts_empty_json_object(self):
        status, headers, body = self.request("POST", "/api/motors/left/stop", {})
        self.assertEqual(200, status)
        self.assertTrue(body["success"])
        self.assertEqual("left", self.motor_port.stop_calls[-1])

    def test_post_change_sensor_mode_executes_command(self):
        status, headers, body = self.request(
            "POST",
            "/api/sensors/us1/mode",
            {"mode": "CM"},
        )
        self.assertEqual(200, status)
        self.assertTrue(body["success"])
        self.assertEqual(("us1", "CM"), self.sensor_port.changed_modes[-1])

    def test_post_change_sensor_mode_requires_mode(self):
        status, headers, body = self.request("POST", "/api/sensors/us1/mode", {})
        self.assertEqual(400, status)
        self.assertEqual(ResultStatuses.INVALID_ARGUMENT, body["status"])
        self.assertEqual(400, body["status_code"])
        self.assertEqual("Required field missing: mode.", body["error"])

    def test_post_rejects_unexpected_json_fields(self):
        status, headers, body = self.request(
            "POST",
            "/api/motors/left/run-timed",
            {"speed_sp": 100, "time_sp": 250, "extra": 1},
        )
        self.assertEqual(400, status)
        self.assertEqual(["extra"], body["data"]["unexpected_fields"])

    def test_post_requires_json_object_body(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2.0)
        conn.request(
            "POST",
            "/api/motors/left/run-timed",
            body="[]",
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()
        self.assertEqual(400, response.status)
        self.assertEqual("JSON body must be an object.", body["error"])

    def test_post_rejects_invalid_json(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2.0)
        conn.request(
            "POST",
            "/api/motors/left/run-timed",
            body="{bad-json",
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()
        self.assertEqual(400, response.status)
        self.assertEqual("Invalid JSON.", body["error"])

    def test_shutdown_requires_valid_token(self):
        status, headers, body = self.request(
            "POST",
            "/api/system/shutdown",
            {"token": "wrong", "confirm": True},
        )
        self.assertEqual(401, status)
        self.assertFalse(body["success"])
        self.assertEqual([], self.shutdown_calls)

    def test_shutdown_requires_confirmation(self):
        status, headers, body = self.request(
            "POST",
            "/api/system/shutdown",
            {"token": TEST_SHUTDOWN_TOKEN},
        )
        self.assertEqual(400, status)
        self.assertIn("confirmation", body["error"])
        self.assertEqual([], self.shutdown_calls)

    def test_shutdown_accepts_token_in_body(self):
        status, headers, body = self.request(
            "POST",
            "/api/system/shutdown",
            {"token": TEST_SHUTDOWN_TOKEN, "confirm": True},
        )
        self.assertEqual(202, status)
        self.assertTrue(body["success"])
        self._wait_for(lambda: self.shutdown_calls)

    def test_restart_accepts_bearer_token_header(self):
        status, headers, body = self.request(
            "POST",
            "/api/system/restart",
            {"confirm": True},
            {"Authorization": "Bearer " + TEST_SHUTDOWN_TOKEN},
        )
        self.assertEqual(202, status)
        self.assertTrue(body["success"])
        self._wait_for(lambda: self.restart_calls)

    def test_shutdown_accepts_custom_token_header(self):
        status, headers, body = self.request(
            "POST",
            "/api/system/shutdown",
            {"confirm": True},
            {"X-Rover-Token": TEST_SHUTDOWN_TOKEN},
        )
        self.assertEqual(202, status)
        self.assertTrue(body["success"])
        self._wait_for(lambda: self.shutdown_calls)

    def test_unknown_post_route_returns_404(self):
        status, headers, body = self.request("POST", "/api/bad", {})
        self.assertEqual(404, status)
        self.assertEqual("Route not found.", body["error"])

    def _wait_for(self, predicate):
        """Waits for an asynchronous callback to execute."""
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Expected asynchronous callback was not called")


class RestApiServerErrorHttpTestCase(unittest.TestCase):
    """Covers REST adapter error branches."""

    def test_command_exceptions_return_500(self):
        port = get_free_port()
        server = RestApiServer(
            FailingCommandService(),
            host="127.0.0.1",
            port=port,
            shutdown_token=None,
            hardware_api_token=None,
            shutdown_confirmation_required=True
        )
        thread = threading.Thread(target=server.start)
        thread.daemon = True
        thread.start()
        deadline = time.time() + 2.0
        while server.http_server is None and time.time() < deadline:
            time.sleep(0.01)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
        conn.request("GET", "/api/state")
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()
        server.stop()
        thread.join(timeout=2.0)
        self.assertEqual(500, response.status)
        self.assertEqual("Internal server error.", body["error"])

    def test_stop_before_start_is_safe(self):
        server = RestApiServer(
            FailingCommandService(),
            host="127.0.0.1",
            port=get_free_port(),
            shutdown_token=None,
            hardware_api_token=None,
            shutdown_confirmation_required=True
        )
        server.stop()
        self.assertIsNone(server.http_server)


if __name__ == "__main__":
    unittest.main()

class RestApiServerCallbackUnavailableTestCase(unittest.TestCase):
    """REST tests for missing lifecycle callbacks and mapped validation errors."""

    def setUp(self):
        self.sensor_port = FakeSensorPort()
        self.motor_port = FakeMotorPort()
        self.controller_port = FakeControllerPort()
        self.state_port = FakeRoverStateQueryPort()
        self.shutdown_calls = []
        self.restart_calls = []
        self.command_service = CommandService(
            sensor_query_port=self.sensor_port,
            sensor_command_port=self.sensor_port,
            motor_query_port=self.motor_port,
            motor_command_port=self.motor_port,
            motor_command_query_port=self.motor_port,
            drive_motor_port=self.motor_port,
            controller_port=self.controller_port,
            rover_state_query_port=self.state_port,
        )
        self.port = get_free_port()
        self.server = RestApiServer(
            command_service=self.command_service,
            host="127.0.0.1",
            port=self.port,
            shutdown_token=TEST_SHUTDOWN_TOKEN,
            hardware_api_token=None,
            shutdown_confirmation_required=True,
            shutdown_callback=None,
            restart_callback=None,
        )
        self.thread = threading.Thread(target=self.server.start)
        self.thread.daemon = True
        self.thread.start()
        self._wait_until_started()

    def tearDown(self):
        self.server.stop()
        self.thread.join(timeout=2.0)

    def _wait_until_started(self):
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=0.2)
                conn.request("OPTIONS", "/api/state")
                conn.getresponse().read()
                conn.close()
                return
            except Exception:
                time.sleep(0.01)
        self.fail("REST server did not start")

    def request(self, method, path, body=None, headers=None):
        request_headers = headers or {}
        raw_body = None
        if body is not None:
            raw_body = json.dumps(body)
            request_headers.setdefault("Content-Type", "application/json")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2.0)
        conn.request(method, path, body=raw_body, headers=request_headers)
        response = conn.getresponse()
        payload = response.read()
        response_headers = dict(response.getheaders())
        conn.close()
        if payload:
            return response.status, response_headers, json.loads(payload.decode("utf-8"))
        return response.status, response_headers, None

    def test_shutdown_without_callback_returns_503(self):
        status, headers, body = self.request(
            "POST",
            "/api/system/shutdown",
            {"token": TEST_SHUTDOWN_TOKEN, "confirm": True},
        )
        self.assertEqual(503, status)
        self.assertEqual("Shutdown unavailable.", body["error"])

    def test_restart_without_callback_returns_503(self):
        status, headers, body = self.request(
            "POST",
            "/api/system/restart",
            {"token": TEST_SHUTDOWN_TOKEN, "confirm": True},
        )
        self.assertEqual(503, status)
        self.assertEqual("Restart unavailable.", body["error"])

    def test_sensor_mode_payload_failure_is_mapped_to_400(self):
        def invalid_mode(code, mode):
            return {"success": False, "error": "Unsupported sensor mode."}

        self.sensor_port.change_sensor_mode = invalid_mode
        status, headers, body = self.request(
            "POST",
            "/api/sensors/us1/mode",
            {"mode": "BAD"},
        )
        self.assertEqual(400, status)
        self.assertEqual("Unsupported sensor mode.", body["error"])
