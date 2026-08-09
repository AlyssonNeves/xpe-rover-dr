#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thin HTTP input adapter for Rover-DR.

HTTP parsing/serialization stays here while application route mapping lives in
``adapters.rest.command_routes``.  This keeps transport concerns independent
from command orchestration and domain services.
"""

import json
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

from adapters.rest.command_routes import CommandRoutes
from app.models import CommandResult
from app.rover_config import REST_HOST, REST_PORT
from services.app_logger import AppLogger


class RestApiServer(object):
    """Exposes Rover-DR application routes over HTTP."""

    MAX_REQUEST_BODY_BYTES = 8192

    def __init__(self, command_service, host=REST_HOST, port=REST_PORT,
                 ev3dev2_motor_gateway=None):
        self.host = host
        self.port = port
        self.routes = CommandRoutes(
            command_service,
            ev3dev2_motor_gateway=ev3dev2_motor_gateway
        )
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
        routes = self.routes
        max_body_bytes = self.MAX_REQUEST_BODY_BYTES

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
                self._execute_request(
                    lambda: routes.route_get(self._path_parts())
                )

            def do_POST(self):
                try:
                    body, error_result = self._read_json_body()
                    if error_result is not None:
                        self._send_result(error_result)
                        return
                    result = routes.route_post(self._path_parts(), body)
                except Exception as exc:
                    AppLogger.error(
                        "Unhandled REST request error: {}".format(exc)
                    )
                    result = CommandResult.internal_error()
                self._send_result(result)

            def do_DELETE(self):
                self._execute_request(
                    lambda: routes.route_delete(self._path_parts())
                )

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
                    "Access-Control-Allow-Headers", "Content-Type"
                )

            def log_message(self, format_string, *args):
                AppLogger.status(
                    "REST {} - {}".format(
                        self.address_string(), format_string % args
                    )
                )

        return RoverRequestHandler
