import http.client
import json
import threading
import time

import adapters.in_rest_api_server as rest_module
from adapters.in_rest_api_server import RestApiServer
from app.command_service import CommandService
from tests.unit.fakes import (
    FakeControllerPort, FakeDrivePort, FakeMotorPort, FakeRoverStatePort, FakeSensorPort,
)


def build_server(gateway=None, shutdown_callback=None, restart_callback=None):
    service = CommandService(
        FakeSensorPort(), FakeMotorPort(), FakeControllerPort(),
        FakeRoverStatePort(), FakeDrivePort()
    )
    return RestApiServer(
        service, host="127.0.0.1", port=0,
        ev3dev2_motor_gateway=gateway,
        shutdown_callback=shutdown_callback,
        restart_callback=restart_callback
    )


def request(server, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.http_server.server_port, timeout=2)
    payload = None if body is None else json.dumps(body)
    request_headers = dict(headers or {})
    if body is not None:
        request_headers.setdefault("Content-Type", "application/json")
    conn.request(method, path, body=payload, headers=request_headers)
    response = conn.getresponse()
    data = response.read().decode("utf-8")
    conn.close()
    return response.status, response.getheaders(), json.loads(data) if data else None


def test_http_server_health_queries_post_options_and_errors():
    server = build_server()
    thread = threading.Thread(target=server.start)
    thread.daemon = True
    thread.start()
    for _ in range(100):
        if getattr(server, "http_server", None) is not None:
            break
        time.sleep(0.01)
    try:
        status, headers, payload = request(server, "GET", "/api/health")
        assert status == 200 and payload["success"] is True
        assert dict(headers)["Cache-Control"] == "no-store"
        assert request(server, "GET", "/api/sensors/TMP")[0] == 200
        assert request(server, "GET", "/api/sensors/UNKNOWN")[0] == 404
        assert request(server, "POST", "/api/drive/tank", {
            "left_speed_sp": 100, "right_speed_sp": 100, "watchdog_ms": 1000
        })[0] == 202
        assert request(server, "POST", "/api/motors/LLM/run-timed", {
            "speed_sp": 100, "time_sp": 100
        })[0] == 202
        assert request(server, "OPTIONS", "/api/sensors")[0] == 204
        assert request(server, "PUT", "/api/sensors")[0] == 405
    finally:
        server.stop()
        thread.join(1)


class FakeGateway(object):
    def catalog(self):
        return {"available": True}


def _start_server(server):
    thread = threading.Thread(target=server.start)
    thread.daemon = True
    thread.start()
    for _ in range(100):
        if getattr(server, "http_server", None) is not None:
            break
        time.sleep(0.01)
    return thread


def test_protected_gateway_and_system_lifecycle(monkeypatch):
    monkeypatch.setattr(rest_module, "REST_SHUTDOWN_TOKEN", "shutdown-secret")
    monkeypatch.setattr(rest_module, "REST_HARDWARE_API_TOKEN", "hardware-secret")
    monkeypatch.setattr(
        rest_module, "REST_SHUTDOWN_CONFIRMATION_REQUIRED", True
    )

    shutdown_event = threading.Event()
    restart_event = threading.Event()
    server = build_server(
        gateway=FakeGateway(),
        shutdown_callback=shutdown_event.set,
        restart_callback=restart_event.set
    )
    thread = _start_server(server)
    try:
        # Gateway credentials are mandatory for every gateway method.
        assert request(
            server, "GET", "/api/ev3dev2/motor/catalog"
        )[0] == 401
        assert request(
            server, "GET", "/api/ev3dev2/motor/catalog",
            headers={"X-Rover-Hardware-Token": "wrong"}
        )[0] == 401
        status, _, payload = request(
            server, "GET", "/api/ev3dev2/motor/catalog",
            headers={"X-Rover-Hardware-Token": "hardware-secret"}
        )
        assert status == 200
        assert payload["data"]["available"] is True

        # Remote lifecycle requests require both authentication and confirmation.
        assert request(
            server, "POST", "/api/system/shutdown", {"confirm": True}
        )[0] == 401
        assert request(
            server, "POST", "/api/system/shutdown",
            {"token": "shutdown-secret"}
        )[0] == 400
        assert request(
            server, "POST", "/api/system/shutdown", {"confirm": True},
            headers={"X-Rover-Token": "shutdown-secret"}
        )[0] == 202
        assert shutdown_event.wait(1.0)

        assert request(
            server, "POST", "/api/system/restart", {"confirm": True},
            headers={"Authorization": "Bearer shutdown-secret"}
        )[0] == 202
        assert restart_event.wait(1.0)
    finally:
        server.stop()
        thread.join(1)
