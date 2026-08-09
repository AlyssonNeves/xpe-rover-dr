#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP input adapter for the Rover-DR read-only REST API."""

import json
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from app.models import CommandActions, CommandResult, CommandTargets
from services.app_logger import AppLogger


class RestApiServer(object):
    """Exposes application queries through a small HTTP/JSON API."""

    def __init__(self, command_service, host="0.0.0.0", port=8080):
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

            def do_GET(self):
                parsed_path = urlparse(self.path)
                path_parts = [
                    part for part in parsed_path.path.strip("/").split("/")
                    if part
                ]

                result = self._route_get(path_parts)
                self._send_result(result)

            def _route_get(self, path_parts):
                if path_parts == ["api", "health"]:
                    return CommandResult(True, data={"status": "ok"})

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

                return CommandResult(False, 404, error="Endpoint not found")

            def _send_result(self, result):
                payload = json.dumps(
                    result.to_dict(), sort_keys=True
                ).encode("utf-8")
                self.send_response(result.status_code)
                self.send_header(
                    "Content-Type", "application/json; charset=utf-8"
                )
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
                self.close_connection = True

            def log_message(self, format_string, *args):
                AppLogger.status(
                    "REST {} - {}".format(
                        self.address_string(), format_string % args
                    )
                )

        return RoverRequestHandler
