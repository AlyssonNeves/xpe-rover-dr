#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Socket-free coverage of REST request dispatch and validation branches."""

import io
import pytest

from adapters.in_rest_api_server import (
    RestApiServer, RoverRequestHandler
)
from adapters.rest.api_routes import ApiRoute
from app.models import CommandResult, ResultStatuses


class FakeCommandService(object):
    def __init__(self, result=None, error=None):
        self.result = result or CommandResult(success=True, data={"ok": True})
        self.error = error
        self.calls = []

    def execute(self, target, action, payload=None):
        self.calls.append((target, action, payload))
        if self.error is not None:
            raise self.error
        return self.result


class FakeRouteTable(object):
    def __init__(self, route=None, params=None):
        self.route = route
        self.params = params or {}

    def resolve(self, method, path_parts):
        del method
        del path_parts
        return self.route, self.params


class FakeGateway(object):
    def __init__(self):
        self.calls = []

    def _record(self, name, *args):
        self.calls.append((name,) + args)
        return {"name": name}

    def catalog(self):
        return self._record("catalog")

    def list_objects(self):
        return self._record("objects")

    def list_operations(self):
        return self._record("operations")

    def module_value(self, member):
        return self._record("member", member)

    def get_property(self, object_id, property_name):
        return self._record("get_property", object_id, property_name)

    def create(self, class_name, args, kwargs, object_id):
        return self._record("create", class_name, args, kwargs, object_id)

    def invoke(self, object_id, method_name, args, kwargs):
        return self._record("invoke", object_id, method_name, args, kwargs)

    def set_property(self, object_id, property_name, value):
        return self._record("set_property", object_id, property_name, value)

    def delete(self, object_id):
        return self._record("delete", object_id)


class HeaderMap(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


def make_handler(command_service=None):
    handler = object.__new__(RoverRequestHandler)
    handler.command_service = command_service or FakeCommandService()
    handler.route_table = FakeRouteTable()
    handler.shutdown_callback = None
    handler.restart_callback = None
    handler.motor_gateway_port = None
    handler.shutdown_token = "shutdown-token"
    handler.hardware_api_token = "hardware-token"
    handler.shutdown_confirmation_required = True
    handler.headers = HeaderMap()
    handler.rfile = io.BytesIO(b"")
    handler.wfile = io.BytesIO()
    handler.path = "/api/state"
    handler.client_address = ("127.0.0.1", 1234)
    handler.close_connection = False
    handler.responses = []
    handler.response_headers = []
    handler.send_response = lambda status: handler.responses.append(status)
    handler.send_header = lambda name, value: handler.response_headers.append(
        (name, value)
    )
    handler.end_headers = lambda: None
    return handler


def set_body(handler, raw):
    data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    handler.headers["Content-Length"] = str(len(data))
    handler.rfile = io.BytesIO(data)


def capture_json(handler):
    captured = []
    handler._send_json = lambda status, payload: captured.append((status, payload))
    return captured


def capture_errors(handler):
    captured = []
    handler._send_error_payload = lambda status, message: captured.append(
        (status, message)
    )
    return captured


def test_dispatch_maps_unknown_command_and_unexpected_errors():
    handler = make_handler()
    errors = capture_errors(handler)
    handler.route_table = FakeRouteTable(None)
    handler._dispatch("GET")
    assert errors[-1] == (404, "Route not found.")

    route = ApiRoute("GET", ("api", "state"), "state", "STATE", "read")
    handler.route_table = FakeRouteTable(route)
    handler.command_service = FakeCommandService(error=RuntimeError("boom"))
    handler._dispatch("GET")
    assert errors[-1] == (500, "Internal server error.")


def test_dispatch_routes_lifecycle_gateway_and_command(monkeypatch):
    handler = make_handler()
    calls = []
    handler._handle_lifecycle = lambda name, route: calls.append(("life", name))
    handler._handle_gateway = lambda route, params: calls.append(("gateway", route.name))
    handler._handle_command = lambda route, params, query: calls.append(("command", route.name))

    lifecycle = ApiRoute("POST", ("api",), "shutdown")
    handler.route_table = FakeRouteTable(lifecycle)
    handler._dispatch("POST")
    gateway = ApiRoute("GET", ("api",), "gateway_catalog")
    handler.route_table = FakeRouteTable(gateway)
    handler._dispatch("GET")
    command = ApiRoute("GET", ("api",), "state", "STATE", "read")
    handler.route_table = FakeRouteTable(command)
    handler._dispatch("GET")
    assert calls == [
        ("life", "shutdown"),
        ("gateway", "gateway_catalog"),
        ("command", "state")
    ]


def test_handle_command_parses_identifiers_queries_and_body():
    service = FakeCommandService()
    handler = make_handler(service)
    captured = capture_json(handler)

    route = ApiRoute("GET", (), "motor_command", "MOTOR", "read")
    handler._handle_command(route, {"command_id": "12"}, {})
    assert service.calls[-1][2]["command_id"] == 12

    route = ApiRoute("GET", (), "motor_commands", "MOTOR", "list")
    handler._handle_command(route, {}, {"code": ["LLM"]})
    assert service.calls[-1][2]["code"] == "LLM"

    route = ApiRoute("GET", (), "drive_telemetry", "DRIVE", "telemetry")
    handler._handle_command(route, {}, {"limit": ["4"]})
    assert service.calls[-1][2]["limit"] == 4
    assert captured[-1][0] == 200


def test_handle_command_rejects_invalid_integer_parameters():
    handler = make_handler()
    errors = capture_errors(handler)
    handler._handle_command(
        ApiRoute("GET", (), "motor_command", "MOTOR", "read"),
        {"command_id": "bad"},
        {}
    )
    assert errors[-1][0] == 400
    handler._handle_command(
        ApiRoute("GET", (), "drive_telemetry", "DRIVE", "read"),
        {},
        {"limit": ["bad"]}
    )
    assert errors[-1][0] == 400


def test_handle_command_post_and_sensor_mode_error_mapping():
    result = CommandResult(
        success=True,
        data={"success": False, "error": "unsupported"}
    )
    handler = make_handler(FakeCommandService(result=result))
    captured = capture_json(handler)
    handler._read_json_body = lambda allowed, required: {"mode": "BAD"}
    route = ApiRoute(
        "POST", (), "sensor_mode", "SENSOR", "change",
        required_fields=("mode",), allowed_fields=("mode",)
    )
    handler._handle_command(route, {"code": "S1"}, {})
    assert captured[-1][0] == 400
    assert captured[-1][1]["status"] == ResultStatuses.INVALID_ARGUMENT


def test_lifecycle_validation_and_callback_execution():
    handler = make_handler()
    errors = capture_errors(handler)
    route = ApiRoute("POST", (), "shutdown", allowed_fields=("token", "confirm"))

    handler._read_json_body = lambda allowed, required: {"token": "wrong", "confirm": True}
    handler._handle_lifecycle("shutdown", route)
    assert errors[-1][0] == 401

    handler._read_json_body = lambda allowed, required: {"token": "shutdown-token"}
    handler._handle_lifecycle("shutdown", route)
    assert errors[-1][0] == 400

    handler._read_json_body = lambda allowed, required: {
        "token": "shutdown-token", "confirm": True
    }
    handler._handle_lifecycle("shutdown", route)
    assert errors[-1][0] == 503

    calls = []
    captured = capture_json(handler)
    handler.shutdown_callback = lambda: calls.append(len(captured))
    handler._handle_lifecycle("shutdown", route)
    assert calls == [1]
    assert captured[-1][0] == 202


def test_token_helpers_support_headers_and_bearer_tokens():
    handler = make_handler()
    handler.headers["Authorization"] = "Bearer shutdown-token"
    assert handler._bearer_token() == "shutdown-token"
    assert handler._lifecycle_token_valid({}) is True
    handler.headers = HeaderMap({"X-Rover-Hardware-Token": "hardware-token"})
    assert handler._hardware_token_valid() is True
    handler.headers = HeaderMap({"Authorization": "Basic abc"})
    assert handler._bearer_token() is None


def test_gateway_handler_validates_authentication_availability_and_errors():
    handler = make_handler()
    errors = capture_errors(handler)
    route = ApiRoute("GET", (), "gateway_catalog")
    handler._handle_gateway(route, {})
    assert errors[-1][0] == 401

    handler.headers["X-Rover-Hardware-Token"] = "hardware-token"
    handler._handle_gateway(route, {})
    assert errors[-1][0] == 503

    class BrokenGateway(object):
        def catalog(self):
            raise ValueError("bad gateway")

    handler.motor_gateway_port = BrokenGateway()
    handler._handle_gateway(route, {})
    assert errors[-1] == (400, "bad gateway")

    handler.motor_gateway_port = FakeGateway()
    captured = capture_json(handler)
    handler._handle_gateway(route, {})
    assert captured[-1][0] == 200


def test_gateway_post_reads_body_and_supports_all_routes():
    handler = make_handler()
    handler.motor_gateway_port = FakeGateway()
    handler.headers["X-Rover-Hardware-Token"] = "hardware-token"
    handler._read_json_body = lambda allowed, required: {"class_name": "LargeMotor"}
    captured = capture_json(handler)
    route = ApiRoute(
        "POST", (), "gateway_create", required_fields=("class_name",),
        allowed_fields=("class_name",)
    )
    handler._handle_gateway(route, {})
    assert captured[-1][0] == 200

    cases = [
        ("gateway_catalog", {}, {}),
        ("gateway_objects", {}, {}),
        ("gateway_operations", {}, {}),
        ("gateway_member", {"member": "OUTPUT_A"}, {}),
        ("gateway_get_property", {"object_id": "o", "property_name": "p"}, {}),
        ("gateway_create", {}, {"class_name": "LargeMotor"}),
        ("gateway_invoke", {"object_id": "o", "method_name": "off"}, {}),
        ("gateway_set_property", {"object_id": "o", "property_name": "p"}, {"value": 1}),
        ("gateway_delete", {"object_id": "o"}, {})
    ]
    for name, params, body in cases:
        assert handler._call_gateway(name, params, body) is not None
    with pytest.raises(ValueError, match="Unsupported"):
        handler._call_gateway("gateway_bad", {}, {})


def test_read_json_body_validates_transport_and_schema():
    handler = make_handler()
    errors = capture_errors(handler)

    handler.headers["Content-Length"] = "bad"
    assert handler._read_json_body((), ()) is None
    assert errors[-1][0] == 400

    set_body(handler, b"{bad")
    assert handler._read_json_body((), ()) is None
    set_body(handler, b"[]")
    assert handler._read_json_body((), ()) is None

    captured = capture_json(handler)
    set_body(handler, b'{"extra": 1}')
    assert handler._read_json_body((), ()) is None
    assert captured[-1][1]["data"]["unexpected_fields"] == ["extra"]

    set_body(handler, b'{}')
    assert handler._read_json_body(("value",), ("value",)) is None
    set_body(handler, b'{"value": 1}')
    assert handler._read_json_body(("value",), ("value",)) == {"value": 1}


def test_send_error_json_cors_and_log_message(monkeypatch):
    handler = make_handler()
    captured = capture_json(handler)
    handler._send_error_payload(404, "missing")
    assert captured[-1][1]["status"] == ResultStatuses.NOT_FOUND

    handler._send_json = RoverRequestHandler._send_json.__get__(handler)
    handler._send_json(200, {"success": True})
    assert handler.responses[-1] == 200
    assert b'"success": true' in handler.wfile.getvalue()
    assert ("Access-Control-Allow-Origin", "*") in handler.response_headers

    messages = []
    monkeypatch.setattr(
        "adapters.in_rest_api_server.AppLogger.status",
        lambda message: messages.append(message)
    )
    handler.log_message("status %s", "ok")
    assert messages


def test_http_method_delegates_and_options_response():
    handler = make_handler()
    calls = []
    handler._dispatch = lambda method: calls.append(method)
    handler.do_GET()
    handler.do_POST()
    handler.do_DELETE()
    assert calls == ["GET", "POST", "DELETE"]
    handler.do_OPTIONS()
    assert handler.responses[-1] == 204
    assert handler.close_connection is True


def test_server_start_stop_and_handler_binding(monkeypatch):
    instances = []

    class FakeHttpServer(object):
        def __init__(self, address, handler_class):
            self.address = address
            self.handler_class = handler_class
            self.timeout = None
            self.closed = False
            instances.append(self)

        def handle_request(self):
            server._stop_event.set()

        def server_close(self):
            self.closed = True

    monkeypatch.setattr(
        "adapters.in_rest_api_server.RoverHttpServer", FakeHttpServer
    )
    server = RestApiServer(
        FakeCommandService(),
        host="127.0.0.1",
        port=8081,
        shutdown_token=None,
        hardware_api_token=None,
        shutdown_confirmation_required=True
    )
    bound = server._create_handler_class()
    assert issubclass(bound, RoverRequestHandler)
    server.start()
    assert instances[0].closed is True
    server.stop()
