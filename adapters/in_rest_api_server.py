#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Declarative HTTP input adapter for the Rover application."""

import hmac
import json
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from adapters.rest.api_routes import ApiRouteTable
from app.models import ResultStatuses
from ports.application_server_port import ApplicationServerPort
from infrastructure.logging.app_logger import AppLogger



HTTP_STATUS_BY_RESULT = {
    ResultStatuses.SUCCESS: 200,
    ResultStatuses.ACCEPTED: 202,
    ResultStatuses.INVALID_ARGUMENT: 400,
    ResultStatuses.NOT_FOUND: 404,
    ResultStatuses.CONFLICT: 409,
    ResultStatuses.UNAVAILABLE: 503,
    ResultStatuses.UNAUTHORIZED: 401,
    ResultStatuses.INTERNAL_ERROR: 500
}



class RoverHttpServer(HTTPServer):
    """HTTP server configured for deterministic repeated startup."""

    allow_reuse_address = True


class RoverRequestHandler(BaseHTTPRequestHandler):
    """Request handler bound to one assembled Rover application."""

    server_version = "RoverDR"
    sys_version = ""
    MAX_REQUEST_BODY_BYTES = 8192

    command_service = None
    shutdown_callback = None
    restart_callback = None
    motor_gateway_port = None
    route_table = None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Allow", "GET, POST, DELETE, OPTIONS")
        self.send_header("Connection", "close")
        self._send_cors_headers()
        self.end_headers()
        self.close_connection = True

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_PUT(self):
        self._send_method_not_allowed()

    def do_PATCH(self):
        self._send_method_not_allowed()

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path_parts = [
            unquote(part) for part in parsed.path.strip("/").split("/")
            if part
        ]
        route, path_params = self.route_table.resolve(method, path_parts)
        if route is None:
            self._send_error_payload(404, "Route not found.")
            return

        try:
            if route.name == "health":
                self._send_json(200, {
                    "success": True,
                    "status": ResultStatuses.SUCCESS,
                    "status_code": 200,
                    "data": {"status": "ok"}
                })
            elif route.name in ("shutdown", "restart"):
                self._handle_lifecycle(route.name, route)
            elif route.name.startswith("gateway_"):
                self._handle_gateway(route, path_params)
            else:
                self._handle_command(
                    route, path_params, parse_qs(parsed.query)
                )
        except Exception as error:
            AppLogger.error(
                "Unexpected REST request error: {}".format(error)
            )
            self._send_error_payload(
                500, "Internal server error."
            )

    def _handle_command(self, route, path_params, query):
        body = {}
        if route.method == "POST":
            body = self._read_json_body(
                route.allowed_fields, route.required_fields
            )
            if body is None:
                return
        payload = dict(path_params)
        payload.update(body)
        if route.name == "motor_command":
            try:
                payload["command_id"] = int(
                    payload.get("command_id")
                )
            except (TypeError, ValueError):
                self._send_error_payload(
                    400, "Parameter command_id must be an integer"
                )
                return
        if route.name == "motor_commands" and query.get("code"):
            payload["code"] = query["code"][0]
        if route.name == "drive_telemetry" and query.get("limit"):
            try:
                payload["limit"] = int(query["limit"][0])
            except (TypeError, ValueError):
                self._send_error_payload(
                    400, "Parameter limit must be an integer"
                )
                return
        try:
            result = self.command_service.execute(
                route.target, route.action, payload or None
            )
        except Exception as error:
            AppLogger.error(
                "Unexpected REST command error: {}".format(error)
            )
            self._send_error_payload(500, "Internal server error.")
            return
        self._send_command_result(result, route.name)

    def _send_command_result(self, result, route_name):
        status_code = HTTP_STATUS_BY_RESULT.get(result.status, 500)
        payload = result.to_dict()
        payload["status_code"] = status_code
        data = payload.get("data")
        if (route_name == "sensor_mode" and
                isinstance(data, dict) and
                data.get("success") is False):
            self._send_json(400, {
                "success": False,
                "status": ResultStatuses.INVALID_ARGUMENT,
                "status_code": 400,
                "error": data.get("error"),
                "data": data
            })
            return
        self._send_json(status_code, payload)

    def _handle_lifecycle(self, operation_name, route):
        body = self._read_json_body(
            route.allowed_fields, route.required_fields
        )
        if body is None:
            return
        if not self._lifecycle_token_valid(body):
            self._send_error_payload(401, "Unauthorized request.")
            return
        if (self.shutdown_confirmation_required and
                body.get("confirm") is not True):
            self._send_error_payload(
                400, "Explicit confirmation is required."
            )
            return
        callback = (
            self.shutdown_callback if operation_name == "shutdown"
            else self.restart_callback
        )
        if callback is None:
            self._send_error_payload(
                503, "{} unavailable.".format(
                    operation_name.capitalize()
                )
            )
            return
        self._send_json(202, {
            "success": True,
            "status": ResultStatuses.ACCEPTED,
            "status_code": 202,
            "data": {
                "message": "Application {} requested.".format(
                    operation_name
                )
            }
        })
        try:
            callback()
        except Exception as error:
            AppLogger.error(
                "Failed to schedule application {}: {}".format(
                    operation_name, error
                )
            )

    def _lifecycle_token_valid(self, body):
        token = body.get("token") or self.headers.get("X-Rover-Token")
        if token is None:
            token = self._bearer_token()
        return self._tokens_equal(token, self.shutdown_token)

    def _handle_gateway(self, route, params):
        if not self._hardware_token_valid():
            self._send_error_payload(
                401, "Unauthorized motor API request."
            )
            return
        if self.motor_gateway_port is None:
            self._send_error_payload(
                503, "ev3dev2.motor gateway is unavailable."
            )
            return
        body = {}
        if route.method == "POST":
            body = self._read_json_body(
                route.allowed_fields, route.required_fields
            )
            if body is None:
                return
        try:
            data = self._call_gateway(route.name, params, body)
        except Exception as error:
            self._send_error_payload(400, str(error))
            return
        self._send_json(200, {
            "success": True,
            "status": ResultStatuses.SUCCESS,
            "status_code": 200,
            "data": data
        })

    def _call_gateway(self, name, params, body):
        if name == "gateway_catalog":
            return self.motor_gateway_port.catalog()
        if name == "gateway_objects":
            return self.motor_gateway_port.list_objects()
        if name == "gateway_operations":
            return self.motor_gateway_port.list_operations()
        if name == "gateway_member":
            return self.motor_gateway_port.module_value(params["member"])
        if name == "gateway_get_property":
            return self.motor_gateway_port.get_property(
                params["object_id"], params["property_name"]
            )
        if name == "gateway_create":
            class_name = body.get("class_name") or body.get("class")
            if not class_name:
                raise ValueError("Required field missing: class_name.")
            return self.motor_gateway_port.create(
                class_name, body.get("args"),
                body.get("kwargs"), body.get("object_id")
            )
        if name == "gateway_invoke":
            return self.motor_gateway_port.invoke(
                params["object_id"], params["method_name"],
                body.get("args"), body.get("kwargs")
            )
        if name == "gateway_set_property":
            return self.motor_gateway_port.set_property(
                params["object_id"], params["property_name"],
                body["value"]
            )
        if name == "gateway_delete":
            return self.motor_gateway_port.delete(params["object_id"])
        raise ValueError("Unsupported gateway route: {}".format(name))

    def _hardware_token_valid(self):
        token = self.headers.get("X-Rover-Hardware-Token")
        if token is None:
            token = self._bearer_token()
        return self._tokens_equal(token, self.hardware_api_token)

    @staticmethod
    def _tokens_equal(provided, expected):
        if provided is None or expected is None:
            return provided == expected
        try:
            return hmac.compare_digest(str(provided), str(expected))
        except TypeError:
            return False

    def _bearer_token(self):
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            return authorization[7:]
        return None

    def _read_json_body(self, allowed_fields, required_fields):
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
            if length < 0 or length > self.MAX_REQUEST_BODY_BYTES:
                raise ValueError
        except (TypeError, ValueError):
            self._send_error_payload(
                400, "Invalid Content-Length header."
            )
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError):
            self._send_error_payload(400, "Invalid JSON.")
            return None
        if not isinstance(body, dict):
            self._send_error_payload(
                400, "JSON body must be an object."
            )
            return None
        unexpected = sorted(set(body).difference(allowed_fields or ()))
        if unexpected:
            self._send_json(400, {
                "success": False,
                "status": ResultStatuses.INVALID_ARGUMENT,
                "status_code": 400,
                "error": "Unexpected JSON fields.",
                "data": {"unexpected_fields": unexpected}
            })
            return None
        for field in required_fields or ():
            if field not in body or body.get(field) is None:
                self._send_error_payload(
                    400, "Required field missing: {}.".format(field)
                )
                return None
        return body

    def _send_method_not_allowed(self):
        self.send_response(405)
        self.send_header("Allow", "GET, POST, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self._send_cors_headers()
        self.end_headers()
        self.close_connection = True

    def _send_error_payload(self, status_code, message):
        semantic = {
            400: ResultStatuses.INVALID_ARGUMENT,
            401: ResultStatuses.UNAUTHORIZED,
            404: ResultStatuses.NOT_FOUND,
            409: ResultStatuses.CONFLICT,
            503: ResultStatuses.UNAVAILABLE,
            500: ResultStatuses.INTERNAL_ERROR
        }.get(status_code, ResultStatuses.INTERNAL_ERROR)
        self._send_json(status_code, {
            "success": False,
            "status": semantic,
            "status_code": status_code,
            "error": message
        })

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, DELETE, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Rover-Token, "
            "X-Rover-Hardware-Token"
        )

    def _send_json(self, status_code, payload):
        response = json.dumps(
            payload, sort_keys=True
        ).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Connection", "close")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(response)
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, format_text, *args):
        AppLogger.status(
            "REST {} - {}".format(
                self.client_address[0], format_text % args
            )
        )


class RestApiServer(ApplicationServerPort):
    """Exposes application ports through a transport-only HTTP adapter."""

    def __init__(self, command_service, host, port, shutdown_token,
                 hardware_api_token, shutdown_confirmation_required,
                 shutdown_callback=None, restart_callback=None,
                 motor_gateway_port=None):
        self.command_service = command_service
        self.host = host
        self.port = port
        self.http_server = None
        self._shutdown_lock = threading.Lock()
        self._stop_event = threading.Event()
        self.shutdown_callback = shutdown_callback
        self.restart_callback = restart_callback
        self.motor_gateway_port = motor_gateway_port
        self.shutdown_token = shutdown_token
        self.hardware_api_token = hardware_api_token
        self.shutdown_confirmation_required = bool(
            shutdown_confirmation_required
        )
        self.route_table = ApiRouteTable()

    def set_shutdown_callback(self, callback):
        self.shutdown_callback = callback

    def set_restart_callback(self, callback):
        self.restart_callback = callback

    def start(self):
        server = RoverHttpServer(
            (self.host, self.port), self._create_handler_class()
        )
        server.timeout = 0.1
        with self._shutdown_lock:
            self._stop_event.clear()
            self.http_server = server
        AppLogger.status(
            "REST server started at {}:{}.".format(self.host, self.port)
        )
        try:
            while not self._stop_event.is_set():
                server.handle_request()
        except Exception as error:
            AppLogger.error("REST server execution error: {}".format(error))
        finally:
            server.server_close()
            with self._shutdown_lock:
                if self.http_server is server:
                    self.http_server = None
            AppLogger.status("REST server stopped.")

    def stop(self):
        with self._shutdown_lock:
            if self.http_server is None:
                return
            self._stop_event.set()
        AppLogger.status("Stopping REST server.")

    def _create_handler_class(self):
        """Binds one immutable application context to the HTTP handler."""
        attributes = {
            "command_service": self.command_service,
            "shutdown_callback": staticmethod(self.shutdown_callback),
            "restart_callback": staticmethod(self.restart_callback),
            "motor_gateway_port": self.motor_gateway_port,
            "route_table": self.route_table,
            "shutdown_token": self.shutdown_token,
            "hardware_api_token": self.hardware_api_token,
            "shutdown_confirmation_required": self.shutdown_confirmation_required
        }
        return type("BoundRoverRequestHandler", (RoverRequestHandler,), attributes)
