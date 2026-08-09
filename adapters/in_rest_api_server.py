#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP input adapter for the Rover-DR validated read-only REST API."""

import json
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

from app.models import CommandActions, CommandResult, CommandTargets
from app.rover_config import REST_HOST, REST_PORT
from services.app_logger import AppLogger


class RestApiServer(object):
    """Exposes validated application queries through a small HTTP/JSON API."""

    def __init__(self, command_service, host=REST_HOST, port=REST_PORT):
        self.command_service = command_service
        self.host = host
        self.port = port
        self.http_server = None
        self._server_lock = threading.Lock()
        self._stop_requested = threading.Event()

    def start(self):
        """Starts the HTTP server and blocks until it is stopped."""
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
        """Requests shutdown when the HTTP server is running."""
        self._stop_requested.set()
        with self._server_lock:
            server = self.http_server
        if server is not None:
            server.shutdown()

    def _create_handler_class(self):
        command_service = self.command_service

        class RoverRequestHandler(BaseHTTPRequestHandler):
            """Handles the read-only routes available in this increment."""

            server_version = "RoverDR"
            sys_version = ""

            def do_OPTIONS(self):
                """Handles CORS preflight for the read-only API."""
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.send_header("Allow", "GET, OPTIONS")
                self._send_cors_headers()
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

            def do_GET(self):
                """Routes a validated GET request and always returns JSON."""
                try:
                    parsed_path = urlparse(self.path)
                    path_parts = self._get_path_parts(parsed_path.path)
                    result = self._route_get(path_parts)
                except Exception as exc:
                    AppLogger.error(
                        "Unhandled REST request error: {}".format(exc)
                    )
                    result = CommandResult.internal_error()

                self._send_result(result)

            def do_POST(self):
                self._send_method_not_allowed()

            def do_PUT(self):
                self._send_method_not_allowed()

            def do_PATCH(self):
                self._send_method_not_allowed()

            def do_DELETE(self):
                self._send_method_not_allowed()

            @staticmethod
            def _get_path_parts(path):
                return [
                    unquote(part)
                    for part in path.strip("/").split("/")
                    if part
                ]

            def _route_get(self, path_parts):
                if path_parts == ["api", "health"]:
                    return CommandResult.ok({"status": "ok"})

                if path_parts == ["api", "rover", "state"]:
                    return command_service.execute(
                        CommandTargets.ROVER,
                        CommandActions.READ_ROVER_STATE
                    )

                if path_parts == ["api", "sensors"]:
                    return command_service.execute(
                        CommandTargets.SENSOR,
                        CommandActions.LIST_SENSORS
                    )
                if path_parts == ["api", "sensors", "all"]:
                    return command_service.execute(
                        CommandTargets.SENSOR,
                        CommandActions.READ_ALL_SENSORS
                    )
                if len(path_parts) == 3 and path_parts[:2] == ["api", "sensors"]:
                    return command_service.execute(
                        CommandTargets.SENSOR,
                        CommandActions.READ_SENSOR,
                        {"code": path_parts[2]}
                    )

                if path_parts == ["api", "motors"]:
                    return command_service.execute(
                        CommandTargets.MOTOR,
                        CommandActions.LIST_MOTORS
                    )
                if path_parts == ["api", "motors", "all"]:
                    return command_service.execute(
                        CommandTargets.MOTOR,
                        CommandActions.READ_ALL_MOTORS
                    )
                if len(path_parts) == 3 and path_parts[:2] == ["api", "motors"]:
                    return command_service.execute(
                        CommandTargets.MOTOR,
                        CommandActions.READ_MOTOR,
                        {"code": path_parts[2]}
                    )

                controller_routes = {
                    ("api", "controller", "status"):
                        CommandActions.READ_CONTROLLER_STATUS,
                    ("api", "controller", "network"):
                        CommandActions.READ_CONTROLLER_NETWORK,
                    ("api", "controller", "battery"):
                        CommandActions.READ_CONTROLLER_BATTERY,
                    ("api", "controller", "system"):
                        CommandActions.READ_CONTROLLER_SYSTEM
                }
                controller_action = controller_routes.get(tuple(path_parts))
                if controller_action is not None:
                    return command_service.execute(
                        CommandTargets.CONTROLLER,
                        controller_action
                    )

                return CommandResult.not_found("Endpoint not found")

            def _send_method_not_allowed(self):
                self._send_result(
                    CommandResult.method_not_allowed(
                        "Only GET and OPTIONS are supported in this API increment"
                    ),
                    allow_header="GET, OPTIONS"
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
                    "Access-Control-Allow-Methods", "GET, OPTIONS"
                )
                self.send_header(
                    "Access-Control-Allow-Headers", "Content-Type"
                )

            def log_message(self, format_string, *args):
                AppLogger.status(
                    "REST {} - {}".format(
                        self.address_string(), format_string % args
                    )
                )

        return RoverRequestHandler
