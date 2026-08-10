#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP-independent declarative routing for Rover-DR application commands."""

from adapters.rest.api_routes import ApiRouteTable
from adapters.rest.routing import GatewayRouter, parse_command_id
from app.models import CommandResult


class CommandRoutes(object):
    """Maps normalized REST paths to application commands and gateway calls."""

    def __init__(self, command_service, ev3dev2_motor_gateway=None):
        self.command_service = command_service
        self.gateway = GatewayRouter(ev3dev2_motor_gateway)
        self.route_table = ApiRouteTable()

    def route_get(self, path_parts):
        return self._route("GET", path_parts, None)

    def route_post(self, path_parts, body):
        return self._route("POST", path_parts, body or {})

    def route_delete(self, path_parts):
        return self._route("DELETE", path_parts, None)

    def _route(self, method, path_parts, body):
        route, path_params = self.route_table.resolve(method, path_parts)
        if route is None:
            return CommandResult.not_found("Endpoint not found")
        if route.name == "health":
            return CommandResult.ok({"status": "ok"})
        if route.kind == "gateway":
            return self._route_gateway(route.name, path_params, body or {})

        params = dict(body or {})
        params.update(path_params)
        if "command_id" in params:
            params["command_id"] = parse_command_id(params["command_id"])
        if not params:
            params = None
        return self.command_service.execute(route.target, route.action, params)

    def _route_gateway(self, name, params, body):
        calls = {
            "gateway_catalog": (self.gateway.catalog, ()),
            "gateway_objects": (self.gateway.list_objects, ()),
            "gateway_operations": (self.gateway.list_operations, ()),
            "gateway_member": (
                self.gateway.module_value, (params.get("member"),)
            ),
            "gateway_get_property": (
                self.gateway.get_property,
                (params.get("object_id"), params.get("property_name"))
            ),
            "gateway_delete": (
                self.gateway.delete, (params.get("object_id"),)
            ),
        }
        call = calls.get(name)
        if call is not None:
            return call[0](*call[1])
        if name == "gateway_create":
            return self.gateway.create(
                body.get("class"), body.get("args"),
                body.get("kwargs"), body.get("object_id")
            )
        if name == "gateway_invoke":
            return self.gateway.invoke(
                params.get("object_id"), params.get("method_name"),
                body.get("args"), body.get("kwargs")
            )
        if name == "gateway_set_property":
            if "value" not in body:
                return CommandResult.bad_request("Field 'value' is required")
            return self.gateway.set_property(
                params.get("object_id"), params.get("property_name"),
                body["value"]
            )
        return CommandResult.not_found("Endpoint not found")
