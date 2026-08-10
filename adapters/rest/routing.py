#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Reusable route matching primitives for the Rover REST adapter."""

from app.models import CommandResult


class Route(object):
    """Describes one HTTP route and its symbolic handler name."""

    def __init__(self, method, pattern, handler_name):
        self.method = method.upper()
        self.pattern = tuple(pattern)
        self.handler_name = handler_name

    def match(self, method, path_parts):
        if method.upper() != self.method or len(path_parts) != len(self.pattern):
            return None
        params = {}
        for expected, actual in zip(self.pattern, path_parts):
            if expected.startswith("{") and expected.endswith("}"):
                params[expected[1:-1]] = actual
            elif expected != actual:
                return None
        return params


class RouteDispatcher(object):
    """Resolves normalized HTTP paths through a declarative route table."""

    def __init__(self, routes=None):
        self.routes = list(routes or [])

    def add(self, method, pattern, handler_name):
        self.routes.append(Route(method, pattern, handler_name))

    def resolve(self, method, path_parts):
        for route in self.routes:
            params = route.match(method, path_parts)
            if params is not None:
                return route.handler_name, params
        return None, None


class GatewayRouter(object):
    """Maps transport requests to explicit motor-gateway operations."""

    def __init__(self, gateway):
        self.gateway = gateway

    def _call(self, operation):
        if self.gateway is None:
            return CommandResult.service_unavailable(
                "ev3dev2.motor gateway is unavailable"
            )
        try:
            return CommandResult.ok(operation())
        except Exception as exc:
            return CommandResult.bad_request(str(exc))

    def catalog(self):
        return self._call(lambda: self.gateway.catalog())

    def list_objects(self):
        return self._call(lambda: self.gateway.list_objects())

    def list_operations(self):
        return self._call(lambda: self.gateway.list_operations())

    def module_value(self, name):
        return self._call(lambda: self.gateway.module_value(name))

    def get_property(self, object_id, property_name):
        return self._call(
            lambda: self.gateway.get_property(object_id, property_name)
        )

    def create(self, class_name, args=None, kwargs=None, object_id=None):
        return self._call(
            lambda: self.gateway.create(class_name, args, kwargs, object_id)
        )

    def invoke(self, object_id, method_name, args=None, kwargs=None):
        return self._call(
            lambda: self.gateway.invoke(object_id, method_name, args, kwargs)
        )

    def set_property(self, object_id, property_name, value):
        return self._call(
            lambda: self.gateway.set_property(object_id, property_name, value)
        )

    def delete(self, object_id):
        return self._call(lambda: self.gateway.delete(object_id))


def parse_command_id(value):
    """Returns an integer command id when possible, preserving legacy ids."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return value
