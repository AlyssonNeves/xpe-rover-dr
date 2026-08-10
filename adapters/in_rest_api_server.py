#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thin HTTP input adapter for Rover-DR.

HTTP parsing, authentication and serialization stay here while application route
mapping lives in ``adapters.rest.command_routes``.  This keeps transport and
security concerns independent from command orchestration and domain services.
"""

import hmac
import json
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

from adapters.rest.command_routes import CommandRoutes
from app.models import CommandResult
from app.rover_config import (
    REST_HARDWARE_API_TOKEN,
    REST_HOST,
    REST_PORT,
    REST_SHUTDOWN_CONFIRMATION_REQUIRED,
    REST_SHUTDOWN_TOKEN,
)
from infrastructure.logging.app_logger import AppLogger
from ports.application_server_port import ApplicationServerPort


class RestApiServer(ApplicationServerPort):
    """Exposes Rover-DR application routes over HTTP."""

    MAX_REQUEST_BODY_BYTES = 8192

    def __init__(self, command_service, host=REST_HOST, port=REST_PORT,
                 ev3dev2_motor_gateway=None, shutdown_callback=None,
                 restart_callback=None):
        self.host = host
        self.port = port
        self.routes = CommandRoutes(
            command_service,
            ev3dev2_motor_gateway=ev3dev2_motor_gateway
        )
        self.shutdown_callback = shutdown_callback
        self.restart_callback = restart_callback
        self.http_server = None
        self._server_lock = threading.Lock()
        self._stop_requested = threading.Event()

    def set_shutdown_callback(self, shutdown_callback):
        """Sets the lifecycle callback used by the protected shutdown route."""
        self.shutdown_callback = shutdown_callback

    def set_restart_callback(self, restart_callback):
        """Sets the lifecycle callback used by the protected restart route."""
        self.restart_callback = restart_callback

    def start(self):
        handler_class = self._create_handler_class()
        server = HTTPServer((self.host, self.port), handler_class)

        with self._server_lock:
            self.http_server = server

        if self._stop_requested.is_set():
            server.server_close()
            with self._server_lock:
                self.http_server = None
            return

        AppLogger.status(
            "REST API listening on http://{}:{}".format(self.host, self.port)
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()
            with self._server_lock:
                if self.http_server is server:
                    self.http_server = None

    def stop(self):
        self._stop_requested.set()
        with self._server_lock:
            server = self.http_server
        if server is not None:
            server.shutdown()

    def _create_handler_class(self):
        routes = self.routes
        max_body_bytes = self.MAX_REQUEST_BODY_BYTES
        shutdown_callback = self.shutdown_callback
        restart_callback = self.restart_callback

        class RoverRequestHandler(BaseHTTPRequestHandler):
            server_version = "RoverDR"
            sys_version = ""

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.send_header("Allow", "GET, POST, DELETE, OPTIONS")
                self._send_cors_headers()
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

            def do_GET(self):
                path_parts = self._path_parts()
                if self._is_gateway_path(path_parts):
                    if not self._require_hardware_api_token():
                        return
                self._execute_request(lambda: routes.route_get(path_parts))

            def do_POST(self):
                try:
                    body, error_result = self._read_json_body()
                    if error_result is not None:
                        self._send_result(error_result)
                        return

                    path_parts = self._path_parts()
                    if path_parts == ["api", "system", "shutdown"]:
                        self._handle_system_operation(
                            "shutdown", body, shutdown_callback
                        )
                        return
                    if path_parts == ["api", "system", "restart"]:
                        self._handle_system_operation(
                            "restart", body, restart_callback
                        )
                        return

                    if self._is_gateway_path(path_parts):
                        if not self._require_hardware_api_token():
                            return

                    result = routes.route_post(path_parts, body)
                except Exception as exc:
                    AppLogger.error(
                        "Unhandled REST request error: {}".format(exc)
                    )
                    result = CommandResult.internal_error()
                self._send_result(result)

            def do_DELETE(self):
                path_parts = self._path_parts()
                if self._is_gateway_path(path_parts):
                    if not self._require_hardware_api_token():
                        return
                self._execute_request(lambda: routes.route_delete(path_parts))

            def do_PUT(self):
                self._send_method_not_allowed()

            def do_PATCH(self):
                self._send_method_not_allowed()

            def _execute_request(self, executor):
                try:
                    result = executor()
                except Exception as exc:
                    AppLogger.error(
                        "Unhandled REST request error: {}".format(exc)
                    )
                    result = CommandResult.internal_error()
                self._send_result(result)

            def _path_parts(self):
                parsed_path = urlparse(self.path)
                return [
                    unquote(part)
                    for part in parsed_path.path.strip("/").split("/")
                    if part
                ]

            def _read_json_body(self):
                raw_length = self.headers.get("Content-Length", "0")
                try:
                    content_length = int(raw_length)
                except (TypeError, ValueError):
                    return None, CommandResult.bad_request(
                        "Invalid Content-Length header"
                    )

                if content_length < 0 or content_length > max_body_bytes:
                    return None, CommandResult.bad_request(
                        "Request body is too large"
                    )

                if content_length == 0:
                    return {}, None

                raw_body = self.rfile.read(content_length)
                try:
                    body = json.loads(raw_body.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    return None, CommandResult.bad_request(
                        "Request body must contain valid JSON"
                    )

                if not isinstance(body, dict):
                    return None, CommandResult.bad_request(
                        "Request body must be a JSON object"
                    )
                return body, None

            def _is_gateway_path(self, path_parts):
                return path_parts[:3] == ["api", "ev3dev2", "motor"]

            def _authorization_bearer(self):
                authorization = self.headers.get("Authorization", "")
                if authorization.startswith("Bearer "):
                    return authorization[len("Bearer "):].strip()
                return None

            def _tokens_match(self, provided, expected):
                if provided is None or expected is None:
                    return False
                provided = str(provided)
                expected = str(expected)
                if not provided or not expected:
                    return False
                return hmac.compare_digest(provided, expected)

            def _require_hardware_api_token(self):
                token = self.headers.get("X-Rover-Hardware-Token")
                if token is None:
                    token = self._authorization_bearer()

                if self._tokens_match(token, REST_HARDWARE_API_TOKEN):
                    return True

                AppLogger.warning("Unauthorized EV3Dev2 motor API request.")
                self._send_result(CommandResult(
                    False,
                    status_code=401,
                    error="Unauthorized hardware API request"
                ))
                return False

            def _shutdown_token_is_valid(self, body):
                token = body.get("token")
                if token is None:
                    token = self.headers.get("X-Rover-Token")
                if token is None:
                    token = self._authorization_bearer()
                return self._tokens_match(token, REST_SHUTDOWN_TOKEN)

            def _handle_system_operation(self, operation, body, callback):
                if not self._shutdown_token_is_valid(body):
                    AppLogger.warning(
                        "Unauthorized remote {} attempt.".format(operation)
                    )
                    self._send_result(CommandResult(
                        False, status_code=401, error="Unauthorized"
                    ))
                    return

                if (
                    REST_SHUTDOWN_CONFIRMATION_REQUIRED
                    and body.get("confirm") is not True
                ):
                    self._send_result(CommandResult.bad_request(
                        "Required confirmation missing. Send confirm=true"
                    ))
                    return

                if callback is None:
                    self._send_result(CommandResult.service_unavailable(
                        "{} unavailable".format(operation.capitalize())
                    ))
                    return

                self._send_result(CommandResult.ok(
                    {"message": "Application {} requested.".format(operation)},
                    status_code=202
                ))

                # The application lifecycle coordinator owns concurrency.
                # The transport callback schedules shutdown/restart and returns
                # immediately; the REST adapter must not create a competing
                # lifecycle thread.
                callback()

            def _send_method_not_allowed(self):
                self._send_result(
                    CommandResult.method_not_allowed(
                        "Only GET, POST, DELETE and OPTIONS are supported"
                    ),
                    allow_header="GET, POST, DELETE, OPTIONS"
                )

            def _send_result(self, result, allow_header=None):
                payload = json.dumps(
                    result.to_dict(), sort_keys=True
                ).encode("utf-8")
                self.send_response(result.status_code)
                self.send_header(
                    "Content-Type", "application/json; charset=utf-8"
                )
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                if allow_header is not None:
                    self.send_header("Allow", allow_header)
                self._send_cors_headers()
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
                self.close_connection = True

            def _send_cors_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header(
                    "Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS"
                )
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type, Authorization, X-Rover-Token, "
                    "X-Rover-Hardware-Token"
                )

            def log_message(self, format_string, *args):
                AppLogger.status(
                    "REST {} - {}".format(
                        self.address_string(), format_string % args
                    )
                )

        return RoverRequestHandler
