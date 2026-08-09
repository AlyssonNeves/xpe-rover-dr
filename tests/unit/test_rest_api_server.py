import http.client
import json
import threading
import time

from adapters.in_rest_api_server import RestApiServer
from app.command_service import CommandService
from tests.unit.fakes import (
    FakeControllerPort, FakeDrivePort, FakeMotorPort, FakeRoverStatePort, FakeSensorPort,
)


def build_server():
    service = CommandService(
        FakeSensorPort(), FakeMotorPort(), FakeControllerPort(),
        FakeRoverStatePort(), FakeDrivePort()
    )
    return RestApiServer(service, host="127.0.0.1", port=0)


def request(server, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.http_server.server_port, timeout=2)
    payload = None if body is None else json.dumps(body)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=payload, headers=headers)
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
