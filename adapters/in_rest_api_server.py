#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP input adapter for Rover-DR queries and queued motor commands."""

import json
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

from app.models import CommandActions, CommandResult, CommandTargets
from app.rover_config import REST_HOST, REST_PORT
from services.app_logger import AppLogger


class RestApiServer(object):
    """Exposes validated Rover-DR queries and motor command orchestration."""

    MAX_REQUEST_BODY_BYTES = 8192

    def __init__(self, command_service, host=REST_HOST, port=REST_PORT):
        self.command_service = command_service
        self.host = host
        self.port = port
        self.http_server = None
        self._server_lock = threading.Lock()
        self._stop_requested = threading.Event()

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
        command_service = self.command_service
        max_body_bytes = self.MAX_REQUEST_BODY_BYTES

        class RoverRequestHandler(BaseHTTPRequestHandler):
            server_version = "RoverDR"
            sys_version = ""

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.send_header("Allow", "GET, POST, OPTIONS")
                self._send_cors_headers()
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

            def do_GET(self):
                try:
                    path_parts = self._path_parts()
                    result = self._route_get(path_parts)
                except Exception as exc:
                    AppLogger.error(
                        "Unhandled REST request error: {}".format(exc)
                    )
                    result = CommandResult.internal_error()
                self._send_result(result)

            def do_POST(self):
                try:
                    path_parts = self._path_parts()
                    body, error_result = self._read_json_body()
                    if error_result is not None:
                        self._send_result(error_result)
                        return
                    result = self._route_post(path_parts, body)
                except Exception as exc:
                    AppLogger.error(
                        "Unhandled REST request error: {}".format(exc)
                    )
                    result = CommandResult.internal_error()
                self._send_result(result)

            def do_PUT(self):
                self._send_method_not_allowed()

            def do_PATCH(self):
                self._send_method_not_allowed()

            def do_DELETE(self):
                self._send_method_not_allowed()

            def _path_parts(self):
                parsed_path = urlparse(self.path)
                return [
                    unquote(part)
                    for part in parsed_path.path.strip("/").split("/")
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

                if path_parts == ["api", "drive", "status"]:
                    return command_service.execute(
                        CommandTargets.DRIVE,
                        CommandActions.READ_DRIVE_STATUS
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

                if path_parts == ["api", "motor-commands"]:
                    return command_service.execute(
                        CommandTargets.MOTOR,
                        CommandActions.LIST_MOTOR_COMMANDS
                    )
                if (
                    len(path_parts) == 3
                    and path_parts[:2] == ["api", "motor-commands"]
                ):
                    try:
                        command_id = int(path_parts[2])
                    except ValueError:
                        command_id = path_parts[2]
                    return command_service.execute(
                        CommandTargets.MOTOR,
                        CommandActions.GET_MOTOR_COMMAND,
                        {"command_id": command_id}
                    )
                if (
                    len(path_parts) == 4
                    and path_parts[:2] == ["api", "motors"]
                    and path_parts[3] == "commands"
                ):
                    return command_service.execute(
                        CommandTargets.MOTOR,
                        CommandActions.LIST_MOTOR_COMMANDS,
                        {"code": path_parts[2]}
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

            def _route_post(self, path_parts, body):
                if path_parts == ["api", "drive", "tank"]:
                    return command_service.execute(
                        CommandTargets.DRIVE,
                        CommandActions.DRIVE_TANK,
                        body
                    )

                drive_routes = {
                    ("api", "drive", "stop"): CommandActions.STOP_DRIVE,
                    ("api", "drive", "reset-odometry"):
                        CommandActions.RESET_DRIVE_ODOMETRY,
                    ("api", "drive", "move-distance"):
                        CommandActions.MOVE_DRIVE_DISTANCE,
                    ("api", "drive", "rotate-angle"):
                        CommandActions.ROTATE_DRIVE_ANGLE,
                    ("api", "drive", "curve-radius"):
                        CommandActions.CURVE_DRIVE_RADIUS,
                }
                drive_action = drive_routes.get(tuple(path_parts))
                if drive_action is not None:
                    return command_service.execute(
                        CommandTargets.DRIVE, drive_action, body
                    )

                if path_parts == ["api", "motors", "synchronized"]:
                    return command_service.execute(
                        CommandTargets.MOTOR,
                        CommandActions.RUN_SYNCHRONIZED_MOTORS,
                        body
                    )

                if (
                    len(path_parts) == 4
                    and path_parts[:2] == ["api", "motors"]
                ):
                    code = path_parts[2]
                    operation = path_parts[3]
                    action_map = {
                        "stop": CommandActions.STOP_MOTOR,
                        "run-timed": CommandActions.RUN_TIMED_MOTOR,
                        "run-forever": CommandActions.RUN_FOREVER_MOTOR,
                        "run-to-rel-pos": CommandActions.RUN_TO_REL_POS_MOTOR,
                        "reset": CommandActions.RESET_MOTOR,
                        "cancel": CommandActions.CANCEL_MOTOR_COMMANDS
                    }
                    action = action_map.get(operation)
                    if action is not None:
                        params = dict(body)
                        params["code"] = code
                        return command_service.execute(
                            CommandTargets.MOTOR, action, params
                        )

                return CommandResult.not_found("Endpoint not found")

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

            def _send_method_not_allowed(self):
                self._send_result(
                    CommandResult.method_not_allowed(
                        "Only GET, POST and OPTIONS are supported"
                    ),
                    allow_header="GET, POST, OPTIONS"
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
                    "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
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
